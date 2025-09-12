import base64
import io
import sys
import re
import html
import textwrap
from pathlib import Path
from typing import Any, List, Dict, Tuple, Set, TextIO
from utils.renderer import MeshRenderer, VIEWPOINTS

from stl.mesh import Mesh
from prompt_toolkit import prompt

from .measure_action import measure_model
from .framework import Context, pipeline_action

@pipeline_action(
    gerund='examining',
    implied_actions=[measure_model],
)
def info(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Get basic info about the model, and AI description if enabled '''

    sizes = ctx.mesh_metrics.sizes()
    mid = ctx.mesh_metrics.midpoints()
    stdout.write(f"Mesh size: x={sizes.x:.2f}, y={sizes.y:.2f}, z={sizes.z:.2f}\n")
    stdout.write(f"Mesh center: x={mid.x:.2f}, y={mid.y:.2f}, z={mid.z:.2f}\n")

    if ctx.options.gemini_key:
        stdout.write("\nAI description:\n")
        describe_model(ctx.mesh, ctx.options.gemini_key, stdout, debug_stdout, ctx.options.interactive)


SerializedImage = Dict[str, Any]
PromptObject = List[Any]

MODEL_COLOR = 'orange'
PLANE_SIZE = 300
PLANE_OPACITY = .2
IMAGE_PIXELS = 768
LLM_NAME = 'gemini-2.5-pro'

VIEWPOINTS_TO_USE = [
    'above_front_left',
    'above_front_right',
    'above_back_left',
    'above_back_right',
    'top',
    'bottom',
]
PROMPT_TEXT = textwrap.dedent('''\
    You are reviewing a rendered STL file of a 3D model that has one or more parts. These images show the model in that file rendered from multiple different angles. The orange color of the part(s) is arbitrarily chosen for the render, do not mention that the parts are orange.. Part(s) are shown on a ground plane with 10mm grid markings; the plane is not part of the model. These images are all from the same model file and depict the same exact part(s) in the same arrangement, but viewed from different angles.

    Describe the shape of the part(s) so that someone who is blind can understand them. Do not describe the model's color, the specific image viewpoints, or anything else about how you are viewing the shapes. Only describe the physical objects themselves.

    Sometimes models may have obvious defects or mistakes. If this model has such defects, be sure to mention them. If there are no noticeable defects, do not mention defects at all.'''
)

def serialize_image(img: 'PIL.Image') -> SerializedImage:
    stream = io.BytesIO()
    img.save(stream, format="png")
    return {'mime_type':'image/png', 'data': base64.b64encode(stream.getvalue()).decode('utf-8')}

def print_token_stats(
    res: 'google.generativeai.types.GenerateContentResponse',
    stream: TextIO,
):
    stream.write(f"Prompt tokens: {res.usage_metadata.prompt_token_count}\n")
    stream.write(f"Candidates tokens: {res.usage_metadata.candidates_token_count}\n")
    stream.write(f"Total tokens: {res.usage_metadata.total_token_count}\n")

def describe_model(mesh: Mesh, gemini_api_key: str, stdout: TextIO, debug_stdout: TextIO, interactive: bool) -> None:
    import google.generativeai as genai  # Slow import

    renderer = MeshRenderer(mesh)
    images = [
        serialize_image(
            renderer.get_image(VIEWPOINTS[vp_name], IMAGE_PIXELS, IMAGE_PIXELS)
        )
        for vp_name in VIEWPOINTS_TO_USE
    ]

    genai.configure(api_key=gemini_api_key)
    llm = genai.GenerativeModel(LLM_NAME)
    chat = llm.start_chat()

    res = chat.send_message([PROMPT_TEXT] + images)
    stdout.write(res.text + "\n")
    print_token_stats(res, debug_stdout)

    if interactive:
        stdout.write("\nYou are in interactive mode and can ask the AI follow-up questions.")
        stdout.write('\nTo stop asking questions, type "stop", "quit", or "exit:\n')

        while True:
            question = prompt("Q: ").strip()
            if question == '':
                continue

            if question.lower() in ['stop', 'quit', 'exit']:
                stdout.write("End of interaction.\n")
                return

            res = chat.send_message(question)
            stdout.write(res.text + "\n")
            print_token_stats(res, debug_stdout)
