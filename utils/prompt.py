import textwrap
from pathlib import Path

# Default AI prompt for model description
DEFAULT_AI_PROMPT = textwrap.dedent('''\
    You are reviewing a rendered STL file of a 3D model that has one or more parts. These images show the model in that file rendered from multiple different angles. The orange color of the part(s) is arbitrarily chosen for the render, do not mention that the parts are orange.. Part(s) are shown on a ground plane with 10mm grid markings; the plane is not part of the model. These images are all from the same model file and depict the same exact part(s) in the same arrangement, but viewed from different angles.

    Describe the shape of the part(s) so that someone who is blind can understand them. Do not describe the model's color, the specific image viewpoints, or anything else about how you are viewing the shapes. Only describe the physical objects themselves.

    Sometimes models may have obvious defects or mistakes. If this model has such defects, be sure to mention them. If there are no noticeable defects, do not mention defects at all.''')

def get_ai_prompt(config_dir: Path) -> str:
    """Get the AI prompt to use - custom if available, otherwise default"""
    custom_prompt_file = config_dir / "prompt.txt"

    if custom_prompt_file.exists():
        print("Using prompt from file") # TODO debug
        with open(custom_prompt_file, 'r', encoding='utf-8') as fh:
            return fh.read().strip()

    print("Using defualt prompt") # TODO debug
    return DEFAULT_AI_PROMPT

def ensure_custom_prompt_exists(config_dir: Path) -> Path:
    """Ensure custom prompt file exists, creating it with default content if needed"""
    prompt_file = config_dir / "prompt.txt"

    if not prompt_file.exists():
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        with open(prompt_file, 'w', encoding='utf-8') as fh:
            fh.write(DEFAULT_AI_PROMPT)

    return prompt_file
