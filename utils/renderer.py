from dataclasses import dataclass
import numpy as np
from stl.mesh import Mesh
import matplotlib.colors as mcolors

Vec = tuple[float, float, float]

@dataclass
class Viewpoint:
    up: Vec
    pos: Vec

@dataclass
class LightSource:
    # See the VTK docs to understand the reference frame for these coordinates:
    # https://vtk.org/doc/nightly/html/classvtkLight.html#ab3fe7a34c7e097744b12832ea4488987
    pos: Vec
    intensity: float

@dataclass
class ColorScheme:
    model_color: str
    bg_color: str
    x_grid_color: str
    y_grid_color: str

VIEWPOINTS = {
    'left': Viewpoint(up=(0, 0, 1), pos=(-1, 0, 0)),
    'right': Viewpoint(up=(0, 0, 1), pos=(1, 0, 0)),
    'back': Viewpoint(up=(0, 0, 1), pos=(0, -1, 0)),
    'front': Viewpoint(up=(0, 0, 1), pos=(0, 1, 0)),
    'bottom': Viewpoint(up=(0, -1, 0), pos=(0, 0, -1)),
    'top': Viewpoint(up=(0, 1, 0), pos=(0, 0, 1)),
    'above_front': Viewpoint(up=(0, 0, 1), pos=(0, -1, 1)),
    'above_front_left': Viewpoint(up=(0, 0, 1), pos=(-1, -1, 1)),
    'above_front_right': Viewpoint(up=(0, 0, 1), pos=(1, -1, 1)),
    # These are "if you're looking at the back, and you rotate your view to the RIGHT or LEFT
    'above_back_left': Viewpoint(up=(0, 0, 1), pos=(1, 1, 1)),
    'above_back_right': Viewpoint(up=(0, 0, 1), pos=(-1, 1, 1)),
}

DEFAULT_COLORS = ColorScheme(
    model_color='orange',
    bg_color='lightgray',
    x_grid_color='green',
    y_grid_color='blue',
)
PLANE_SIZE = 300
PLANE_OPACITY = .2

LIGHT_POSITIONS = [
    # These were chosen via trial and error; the lighting probably could be better
    LightSource((1, 0, 1), 1),
    LightSource((-.5, 0, 1), .4),
    LightSource((0, .8, 1), .3),
]

def _move_to_origin(original_mesh: Mesh) -> Mesh:
    """ Center the object on the Z axis and raise it above the x-y plane """
    min_corner = np.min(original_mesh.vectors, axis=(0, 1))
    max_corner = np.max(original_mesh.vectors, axis=(0, 1))

    # Compute the centroid in X and Y (to center it on the Z-axis)
    center_x = (min_corner[0] + max_corner[0]) / 2
    center_y = (min_corner[1] + max_corner[1]) / 2

    # Compute the translation vector
    translation = np.array([-center_x, -center_y, -min_corner[2]])

    # Create a new mesh object with translated vertices
    translated_mesh = Mesh(np.copy(original_mesh.data))
    translated_mesh.vectors += translation  # Apply translation

    return translated_mesh


class MeshRenderer:
    '''
    Important: Multiple active instances of this class at once will not work.
    '''

    def __init__(self, mesh: Mesh, colors=DEFAULT_COLORS):
        """
        Plots the given model as the current figure.
        """
        # Slow imports
        import vtk
        import vtkplotlib as vpl

        vpl.close()  # In case there's an open figure; close it

        # Add the model mesh
        mesh = _move_to_origin(mesh)
        vpl.figure()
        vpl.mesh_plot(mesh, color=colors.model_color)

        # Set up lighting
        renderer = vpl.gcf().renderer
        renderer.SetBackground(*mcolors.to_rgb(colors.bg_color))
        # TODO SSAO creates weird artifacts on smaller objects because the parameters should be
        # tuned to the scene size, which I haven't done. I'll re-enable it once that's fixed
        #renderer.SetUseSSAO(True)  # Enable ambient occlusion
        for light_spec in LIGHT_POSITIONS:
            light = vtk.vtkLight()
            light.SetLightTypeToCameraLight()
            light.SetPositional(True)
            light.SetPosition(*light_spec.pos)
            light.SetColor(1, 1, 1)  # White
            light.SetIntensity(light_spec.intensity)
            renderer.AddLight(light)

        # Add plane lines
        half_plane = PLANE_SIZE // 2 
        plane_plots = []
        for x in range(0, half_plane + 1, 10):
            plane_plots.append(vpl.plot(
                [(x, -half_plane, 0), (x, half_plane, 0)],
                color=colors.x_grid_color,
                opacity=PLANE_OPACITY,
            ))
            plane_plots.append(vpl.plot(
                [(-x, -half_plane, 0), (-x, half_plane, 0)],
                color=colors.x_grid_color,
                opacity=PLANE_OPACITY,
            ))

        for y in range(0, half_plane + 1, 10):
            plane_plots.append(vpl.plot(
                [(-half_plane, y, 0), (half_plane, y, 0)],
                color=colors.y_grid_color,
                opacity=PLANE_OPACITY,
            ))
            plane_plots.append(vpl.plot(
                [(-half_plane, -y, 0), (half_plane, -y, 0)],
                color=colors.y_grid_color,
                opacity=PLANE_OPACITY,
            ))
        
        self._plane_plots = plane_plots

    def get_image(self, vp: Viewpoint, width: int, height: int) -> 'PIL.Image':
        from PIL import Image  # Slow import
        import vtkplotlib as vpl  # Slow import

        # Hide the plane lines during the automatic zoom out that happens, so it
        # only tries to fit the actual model in the viewport
        for pp in self._plane_plots:
            pp.visible = False

        vpl.view(up_view=vp.up, camera_position=vp.pos)
        vpl.reset_camera()

        for pp in self._plane_plots:
            pp.visible = True

        return Image.fromarray(vpl.screenshot_fig(pixels=(width, height), off_screen=True))
