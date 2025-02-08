import base64
import io
import sys
import re
import html
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Dict, Tuple, Set, TextIO

import numpy as np
from stl.mesh import Mesh

from .measure_action import measure_model
from .framework import Context, pipeline_action

@pipeline_action(
    gerund='examining',
    implied_actions=[measure_model],
)
def info(ctx: Context, stdout: TextIO, __):
    ''' Get basic dimensional info about the model, and AI description if enabled '''

    sizes = ctx.mesh_metrics.sizes()
    mid = ctx.mesh_metrics.midpoints()
    stdout.write(f"Mesh size: x={sizes.x:.2f}, y={sizes.y:.2f}, z={sizes.z:.2f}\n")
    stdout.write(f"Mesh center: x={mid.x:.2f}, y={mid.y:.2f}, z={mid.z:.2f}\n")

    if ctx.options.gemini_key:
        stdout.write("\nAI description:\n")
        stdout.write(describe_model(ctx.mesh, ctx.options.gemini_key))
        stdout.write("\n")


Vec = Tuple[float, float, float]
SerializedImage = Dict[str, Any]
PromptObject = List[Any]

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

VIEWPOINTS = {
    'left': Viewpoint(up=(0, 0, 1), pos=(-1, 0, 0)),
    'right': Viewpoint(up=(0, 0, 1), pos=(1, 0, 0)),
    'back': Viewpoint(up=(0, 0, 1), pos=(0, -1, 0)),
    'front': Viewpoint(up=(0, 0, 1), pos=(0, 1, 0)),
    'bottom': Viewpoint(up=(0, -1, 0), pos=(0, 0, -1)),
    'top': Viewpoint(up=(0, 1, 0), pos=(0, 0, 1)),
    'iso_front_left': Viewpoint(up=(0, 0, 1), pos=(-1, -1, 1)),
    'iso_front_right': Viewpoint(up=(0, 0, 1), pos=(1, -1, 1)),
    # These are "if you're looking at the back, and you rotate your view to the RIGHT or LEFT
    'iso_back_left': Viewpoint(up=(0, 0, 1), pos=(1, 1, 1)),
    'iso_back_right': Viewpoint(up=(0, 0, 1), pos=(-1, 1, 1)),
}

LIGHT_POSITIONS = [
    # These were chosen via trial and error; the lighting probably could be better
    LightSource((1, 0, 1), 1),
    LightSource((-.5, 0, 1), .4),
    LightSource((0, .8, 1), .3),
]

MODEL_COLOR = 'orange'
PLANE_SIZE = 300
PLANE_OPACITY = .2
IMAGE_PIXELS = 768
LLM_NAME = "gemini-1.5-pro"

VIEWPOINTS_TO_USE = [
    'iso_front_left',
    'iso_front_right',
    'iso_back_left',
    'iso_back_right',
    'top',
    'bottom',
]
PROMPT_TEXT = textwrap.dedent('''\
    You are reviewing a rendered STL file of a 3D model that has one or more parts. These images show the model in that file rendered from multiple different angles. The orange color of the part(s) is arbitrarily chosen for the render, do not mention that the parts are orange.. Part(s) are shown on a ground plane with 10mm grid markings; the plane is not part of the model. These images are all from the same model file and depict the same exact part(s) in the same arrangement, but viewed from different angles.

    Describe the shape of the part(s) so that someone who is blind can understand them. Do not describe the model's color, the specific image viewpoints, or anything else about how you are viewing the shapes. Only describe the physical objects themselves.

    Sometimes models may have obvious defects or mistakes. If this model has such defects, be sure to mention them. If there are no noticeable defects, do not mention defects at all.'''
)

def move_to_origin(original_mesh: Mesh) -> Mesh:
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

def plot_mesh(mesh: Mesh) -> List[Any]:  # TODO type is plot
    """
    Plots the given model as the current figure.
    """
    # Slow imports
    import vtk
    import vtkplotlib as vpl

    vpl.close()  # In case there's an open figure; close it

    # Add the model mesh
    mesh = move_to_origin(mesh)
    vpl.figure()
    vpl.mesh_plot(mesh, color=MODEL_COLOR)

    # Set up lighting
    renderer = vpl.gcf().renderer
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
            color='green',
            opacity=PLANE_OPACITY,
        ))
        plane_plots.append(vpl.plot(
            [(-x, -half_plane, 0), (-x, half_plane, 0)],
            color='green',
            opacity=PLANE_OPACITY,
        ))

    for y in range(0, half_plane + 1, 10):
        plane_plots.append(vpl.plot(
            [(-half_plane, y, 0), (half_plane, y, 0)],
            color='blue',
            opacity=PLANE_OPACITY,
        ))
        plane_plots.append(vpl.plot(
            [(-half_plane, -y, 0), (half_plane, -y, 0)],
            color='blue',
            opacity=PLANE_OPACITY,
        ))

    return plane_plots

def serialize_image(image_array: np.ndarray) -> SerializedImage:
    from PIL import Image  # Slow import
    img = Image.fromarray(image_array)
    stream = io.BytesIO()
    img.save(stream, format="png")
    return {'mime_type':'image/png', 'data': base64.b64encode(stream.getvalue()).decode('utf-8')}

def get_image(plane_plots, viewpoint_name: str) -> SerializedImage: # TODO
    """
    Returns a serialized image dict in the form that Gemini likes.
    Assumes the model has already been loaded
    """
    import vtkplotlib as vpl  # Slow import

    vp = VIEWPOINTS[viewpoint_name]

    for pp in plane_plots:
        pp.visible = False

    # Hide the plane lines during the automatic zoom out that happens, so it
    # only tries to fit the actual model in the viewport
    vpl.view(up_view=vp.up, camera_position=vp.pos)
    vpl.reset_camera()

    for pp in plane_plots:
        pp.visible = True

    return serialize_image(vpl.screenshot_fig(pixels=(IMAGE_PIXELS, IMAGE_PIXELS), off_screen=True))

def describe_model(mesh: Mesh, gemini_api_key: str) -> str:
    import google.generativeai as genai  # Slow import

    plane_plots = plot_mesh(mesh)
    images = [get_image(plane_plots, vp_name) for vp_name in VIEWPOINTS_TO_USE]

    genai.configure(api_key=gemini_api_key)
    llm = genai.GenerativeModel(LLM_NAME)

    return llm.generate_content([PROMPT_TEXT] + images).text
