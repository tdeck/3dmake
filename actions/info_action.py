import base64
import io
import sys
import re
import html
import textwrap
from pathlib import Path
from typing import Any, List, Dict, TextIO, Optional
from utils.renderer import MeshRenderer, VIEWPOINTS

from stl.mesh import Mesh

from .mesh_actions import measure_mesh
from .framework import Context, pipeline_action
from utils.llm_prompt import get_ai_prompt
from utils.user_prompts import prompt

@pipeline_action(
    gerund='examining',
    implied_actions=[measure_mesh],
    input_file_type='.stl',
    last_in_chain=True,
)
def info(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Get basic info about the model, and AI description if enabled '''

    sizes = ctx.mesh_metrics.sizes()
    mid = ctx.mesh_metrics.midpoints()
    stdout.write(f"Mesh size: x={sizes.x:.2f}, y={sizes.y:.2f}, z={sizes.z:.2f}\n")
    stdout.write(f"Mesh center: x={mid.x:.2f}, y={mid.y:.2f}, z={mid.z:.2f}\n")

    if ctx.options.openrouter_key or ctx.options.gemini_key or ctx.options.openai_compat_host:
        stdout.write("\nAI description:\n")
        describe_model(
            mesh=ctx.mesh,
            gemini_api_key=ctx.options.gemini_key,
            openrouter_api_key=ctx.options.openrouter_key,
            openai_compat_host=ctx.options.openai_compat_host,
            openai_api_key=ctx.options.openai_api_key,
            llm_name=ctx.options.llm_name,
            stdout=stdout,
            debug_stdout=debug_stdout,
            interactive=ctx.options.interactive,
            prompt_text=get_ai_prompt(ctx.config_dir),
        )


PromptObject = List[Any]

MODEL_COLOR = 'orange'
PLANE_SIZE = 300
PLANE_OPACITY = .2
IMAGE_PIXELS = 768

VIEWPOINTS_TO_USE = [
    'above_front_left',
    'above_front_right',
    'above_back_left',
    'above_back_right',
    'top',
    'bottom',
]

def print_gemini_token_stats(res: Any, stream: TextIO) -> None:
    stream.write(f"Prompt tokens: {res.usage_metadata.prompt_token_count}\n")
    stream.write(f"Candidates tokens: {res.usage_metadata.candidates_token_count}\n")
    stream.write(f"Total tokens: {res.usage_metadata.total_token_count}\n")

def print_openai_token_stats(completion: Any, stream: TextIO) -> None:
    if hasattr(completion, 'usage') and completion.usage:
        stream.write(f"Prompt tokens: {completion.usage.prompt_tokens}\n")
        stream.write(f"Completion tokens: {completion.usage.completion_tokens}\n")
        stream.write(f"Total tokens: {completion.usage.total_tokens}\n")

def render_png_images(mesh: Mesh) -> List[bytes]:
    renderer = MeshRenderer(mesh)
    images = []
    for vp_name in VIEWPOINTS_TO_USE:
        stream = io.BytesIO()
        renderer.get_image(VIEWPOINTS[vp_name], IMAGE_PIXELS, IMAGE_PIXELS).save(stream, format="png")
        images.append(stream.getvalue())
    return images

def build_openai_image_content(prompt_text: str, images: List[bytes]) -> List[Dict]:
    content = [{"type": "text", "text": prompt_text}]
    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64.b64encode(img).decode()}"}
        })
    return content

def describe_model(
    mesh: Mesh,
    gemini_api_key: Optional[str],
    openrouter_api_key: Optional[str],
    llm_name: str,
    openai_compat_host: Optional[str],
    openai_api_key: Optional[str],
    stdout: TextIO,
    debug_stdout: TextIO,
    interactive: bool,
    prompt_text: str,
) -> None:
    """Route to the correct backend based on which credentials/host are configured.

    Priority order: openai_compat_host > openrouter > gemini.
    openai_compat_host covers Ollama, LM Studio, llama.cpp, ramalama, and any
    other server that exposes an OpenAI-compatible /v1 endpoint.
    """
    if openai_compat_host:
        describe_model_openai_compat(
            mesh,
            openai_compat_host,
            api_key=openai_api_key or "none",
            llm_name=llm_name,
            stdout=stdout, 
            debug_stdout=debug_stdout,
            interactive=interactive, 
            prompt_text=prompt_text,
        )
    elif openrouter_api_key:
        describe_model_openai_compat(
            mesh, 
            base_url="https://openrouter.ai/api/v1", 
            api_key=openrouter_api_key,
            llm_name=llm_name, 
            stdout=stdout, 
            debug_stdout=debug_stdout,
            interactive=interactive, 
            prompt_text=prompt_text,
        )
    elif gemini_api_key:
        describe_model_gemini(
            mesh, 
            gemini_api_key, 
            llm_name, 
            stdout, 
            debug_stdout, 
            interactive, 
            prompt_text)


def describe_model_openai_compat(
    mesh: Mesh,
    base_url: str,
    api_key: Optional[str],
    llm_name: str,
    stdout: TextIO,
    debug_stdout: TextIO,
    interactive: bool,
    prompt_text: str,
) -> None:
    """Shared implementation for common OpenAI-compatible backends.

    Works out of the box with common local llm servers exposing a /v1/chat/completions endpoint

    Pass the raw host for local servers (the /v1 suffix is appended automatically
    if the URL does not already end with /v1 or /v1/).
    """
    from openai import OpenAI  # Slow import — kept lazy

    # Normalise the base_url: local servers are typically given as bare hosts
    # (e.g. "http://localhost:11434"), but the OpenAI client expects a /v1 path.
    if not base_url.rstrip('/').endswith('/v1'):
        base_url = base_url.rstrip('/') + '/v1'

    debug_stdout.write(f"Using model {llm_name} at {base_url}\n")

    images = render_png_images(mesh)
    content = build_openai_image_content(prompt_text, images)

    client = OpenAI(base_url=base_url, api_key=api_key)

    completion = client.chat.completions.create(
        model=llm_name,
        messages=[{"role": "user", "content": content}],
    )
    response_text = completion.choices[0].message.content
    stdout.write(response_text + "\n")
    print_openai_token_stats(completion, debug_stdout)

    if interactive:
        stdout.write("\nYou are in interactive mode and can ask the AI follow-up questions.")
        stdout.write('\nTo stop asking questions, type "stop", "quit", or "exit":\n')

        conversation = [
            {"role": "user", "content": content},
            {"role": "assistant", "content": response_text},
        ]

        while True:
            question = prompt("Q: ").strip()
            if question == '' or question.lower() in ['stop', 'quit', 'exit']:
                if question.lower() in ['stop', 'quit', 'exit']:
                    stdout.write("End of interaction.\n")
                return

            conversation.append({"role": "user", "content": question})
            completion = client.chat.completions.create(model=llm_name, messages=conversation)
            response_text = completion.choices[0].message.content
            stdout.write(response_text + "\n")
            conversation.append({"role": "assistant", "content": response_text})
            print_openai_token_stats(completion, debug_stdout)


def describe_model_gemini(
    mesh: Mesh,
    gemini_api_key: str,
    llm_name: str,
    stdout: TextIO,
    debug_stdout: TextIO,
    interactive: bool,
    prompt_text: str,
) -> None:
    from google import genai  # Slow import
    from google.genai import types

    # Fix up the llm name if they accidentally entered the OpenRouter version
    # just as a convenience
    if llm_name.startswith('google/'):
        llm_name = llm_name[7:]

    debug_stdout.write(f"Using Gemini model {llm_name}\n")

    images = render_png_images(mesh)

    client = genai.Client(api_key=gemini_api_key)
    chat = client.chats.create(model=llm_name)

    parts = [prompt_text] + [
        types.Part.from_bytes(data=img, mime_type='image/png')
        for img in images
    ]

    res = chat.send_message(parts)
    stdout.write(res.text + "\n")
    print_gemini_token_stats(res, debug_stdout)

    if interactive:
        stdout.write("\nYou are in interactive mode and can ask the AI follow-up questions.")
        stdout.write('\nTo stop asking questions, type "stop", "quit", or "exit":\n')

        while True:
            question = prompt("Q: ").strip()
            if question == '' or question.lower() in ['stop', 'quit', 'exit']:
                if question.lower() in ['stop', 'quit', 'exit']:
                    stdout.write("End of interaction.\n")
                return

            res = chat.send_message(question)
            stdout.write(res.text + "\n")
            print_gemini_token_stats(res, debug_stdout)
