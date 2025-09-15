import base64
import io
import sys
import re
import html
import textwrap
from pathlib import Path
from typing import Any, List, Dict, Tuple, Set, TextIO, Optional
from utils.renderer import MeshRenderer, VIEWPOINTS

from stl.mesh import Mesh
from prompt_toolkit import prompt

from .measure_action import measure_model
from .framework import Context, pipeline_action
from utils.prompt import get_ai_prompt

@pipeline_action(
    gerund='examining',
    implied_actions=[measure_model],
    last_in_chain=True,
)
def info(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Get basic info about the model, and AI description if enabled '''

    sizes = ctx.mesh_metrics.sizes()
    mid = ctx.mesh_metrics.midpoints()
    stdout.write(f"Mesh size: x={sizes.x:.2f}, y={sizes.y:.2f}, z={sizes.z:.2f}\n")
    stdout.write(f"Mesh center: x={mid.x:.2f}, y={mid.y:.2f}, z={mid.z:.2f}\n")

    if ctx.options.openrouter_key or ctx.options.gemini_key:
        stdout.write("\nAI description:\n")
        describe_model(
            mesh=ctx.mesh,
            gemini_api_key=ctx.options.gemini_key,
            openrouter_api_key=ctx.options.openrouter_key,
            llm_name=ctx.options.llm_name,
            stdout=stdout,
            debug_stdout=debug_stdout,
            interactive=ctx.options.interactive,
            prompt_text=get_ai_prompt(ctx.config_dir),
        )


SerializedImage = Dict[str, Any]
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

def serialize_image(img: 'PIL.Image') -> SerializedImage:
    stream = io.BytesIO()
    img.save(stream, format="png")
    return {'mime_type':'image/png', 'data': base64.b64encode(stream.getvalue()).decode('utf-8')}

def print_gemini_token_stats(
    res: 'google.generativeai.types.GenerateContentResponse',
    stream: TextIO,
):
    stream.write(f"Prompt tokens: {res.usage_metadata.prompt_token_count}\n")
    stream.write(f"Candidates tokens: {res.usage_metadata.candidates_token_count}\n")
    stream.write(f"Total tokens: {res.usage_metadata.total_token_count}\n")

def describe_model(
    mesh: Mesh,
    gemini_api_key: Optional[str],
    openrouter_api_key: Optional[str],
    llm_name: str,
    stdout: TextIO,
    debug_stdout: TextIO,
    interactive: bool,
    prompt_text: str,
) -> None:
    if openrouter_api_key:
        describe_model_openrouter(mesh, openrouter_api_key, llm_name, stdout, debug_stdout, interactive, prompt_text)
    elif gemini_api_key:
        describe_model_gemini(mesh, gemini_api_key, llm_name, stdout, debug_stdout, interactive, prompt_text)

def describe_model_gemini(
    mesh: Mesh,
    gemini_api_key: str,
    llm_name: str,
    stdout: TextIO,
    debug_stdout: TextIO,
    interactive: bool,
    prompt_text: str,
) -> None:
    import google.generativeai as genai  # Slow import
    debug_stdout.write(f"Using Gemini model {llm_name}\n")

    renderer = MeshRenderer(mesh)
    images = [
        serialize_image(
            renderer.get_image(VIEWPOINTS[vp_name], IMAGE_PIXELS, IMAGE_PIXELS)
        )
        for vp_name in VIEWPOINTS_TO_USE
    ]

    genai.configure(api_key=gemini_api_key)
    llm = genai.GenerativeModel(llm_name)
    chat = llm.start_chat()

    res = chat.send_message([prompt_text] + images)
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



def describe_model_openrouter(
    mesh: Mesh,
    openrouter_api_key: str,
    llm_name: str,
    stdout: TextIO,
    debug_stdout: TextIO,
    interactive: bool,
    prompt_text: str,
) -> None:
    from openai import OpenAI  # Slow import
    debug_stdout.write(f"Using OpenRouter model {llm_name}\n")

    renderer = MeshRenderer(mesh)
    images = [
        serialize_image(
            renderer.get_image(VIEWPOINTS[vp_name], IMAGE_PIXELS, IMAGE_PIXELS)
        )
        for vp_name in VIEWPOINTS_TO_USE
    ]

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_api_key)

    content = [{"type": "text", "text": prompt_text}]
    for img_data in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img_data['mime_type']};base64,{img_data['data']}"}
        })

    completion = client.chat.completions.create(model=llm_name, messages=[{"role": "user", "content": content}])
    response_text = completion.choices[0].message.content
    stdout.write(response_text + "\n")

    if hasattr(completion, 'usage') and completion.usage:
        debug_stdout.write(f"Prompt tokens: {completion.usage.prompt_tokens}\n")
        debug_stdout.write(f"Completion tokens: {completion.usage.completion_tokens}\n")
        debug_stdout.write(f"Total tokens: {completion.usage.total_tokens}\n")

    if interactive:
        stdout.write("\nYou are in interactive mode and can ask the AI follow-up questions.")
        stdout.write('\nTo stop asking questions, type "stop", "quit", or "exit":\n')

        conversation = [{"role": "user", "content": content}, {"role": "assistant", "content": response_text}]

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

            if hasattr(completion, 'usage') and completion.usage:
                debug_stdout.write(f"Total tokens: {completion.usage.total_tokens}\n")
