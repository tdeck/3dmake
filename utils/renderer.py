from dataclasses import dataclass
from typing import Tuple
import numpy as np
from PIL import Image, ImageDraw
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

@dataclass
class Axis:
    name: str
    vector: Vec
    arrow_color: Tuple[int, int, int]


AXIS_ARROW_RADIUS = 30
AXIS_ARROW_CENTER_FROM_EDGE = 45
AXIS_ARROW_OPACITY = 160
AXIS_ARROWHEAD_LENGTH = 8
AXIS_ARROW_LABEL_OFFSET = 12
AXES = [
    Axis(name='X', vector=(1, 0, 0), arrow_color=(0, 180, 0)),
    Axis(name='Y', vector=(0, 1, 0), arrow_color=(0, 0, 255)),
    Axis(name='Z', vector=(0, 0, 1), arrow_color=(220, 0, 0)),
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


def _project_axis_to_screen(axis_3d: Vec, vp_pos: Vec, vp_up: Vec) -> tuple[float, float]:
    '''
    Projects a coordinate axis's direction in the given 2D viewport.
    '''
    forward = -np.array(vp_pos, dtype=float)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, vp_up)
    right /= np.linalg.norm(right)
    cam_up = np.cross(right, forward)
    return (np.dot(axis_3d, right), np.dot(axis_3d, cam_up))

def _add_axis_arrows(image: Image.Image, vp: Viewpoint) -> Image.Image:
    overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    cx = image.width - AXIS_ARROW_CENTER_FROM_EDGE
    cy = image.height - AXIS_ARROW_CENTER_FROM_EDGE

    for axis in AXES:
        sx, sy = _project_axis_to_screen(axis.vector, vp.pos, vp.up)
        if sx * sx + sy * sy < 0.01: # Hide axes perpendicular to screen
            continue
        ex = cx + sx * AXIS_ARROW_RADIUS
        ey = cy - sy * AXIS_ARROW_RADIUS
        rgba = (*axis.arrow_color, AXIS_ARROW_OPACITY)
        draw.line([(cx, cy), (ex, ey)], fill=rgba, width=2)

        angle = np.arctan2(-sy, sx)
        for da in [2.5, -2.5]: # Arrow line rotation angle (radians)
            hx = ex + AXIS_ARROWHEAD_LENGTH * np.cos(angle + da)
            hy = ey + AXIS_ARROWHEAD_LENGTH * np.sin(angle + da)
            draw.line([(ex, ey), (hx, hy)], fill=rgba, width=2)

        lx = cx + sx * (AXIS_ARROW_RADIUS + AXIS_ARROW_LABEL_OFFSET)
        ly = cy - sy * (AXIS_ARROW_RADIUS + AXIS_ARROW_LABEL_OFFSET)
        draw.text((lx - 4, ly - 6), axis.name, fill=rgba) # -4, -6 roughly center letter

    return Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')


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

    def get_image(self, vp: Viewpoint, width: int, height: int, axis_arrows: bool = False) -> Image.Image:
        import vtkplotlib as vpl  # Slow import

        # Hide the plane lines during the automatic zoom out that happens, so it
        # only tries to fit the actual model in the viewport
        for pp in self._plane_plots:
            pp.visible = False

        vpl.view(up_view=vp.up, camera_position=vp.pos)
        vpl.reset_camera()

        for pp in self._plane_plots:
            pp.visible = True

        image = Image.fromarray(vpl.screenshot_fig(pixels=(width, height), off_screen=True))
        if axis_arrows:
            image = _add_axis_arrows(image, vp)
        return image
