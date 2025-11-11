from pathlib import Path
from typing import TextIO
import shutil

from prompt_toolkit import prompt

from .framework import Context, isolated_action

@isolated_action(needs_options=False)
def new(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Create a new 3DMake project directory structure '''

    proj_dir = prompt("Choose a project directory name (press ENTER for current dir): ").strip()
    if proj_dir == '':
        proj_dir = '.'  # Current directory

    proj_path = Path(proj_dir)

    # Create project dirs
    proj_path.mkdir(exist_ok=True)
    (proj_path / "src").mkdir(exist_ok=True)
    (proj_path / "build").mkdir(exist_ok=True)

    # Create empty 3dmake.toml if none exists
    toml_file = proj_path / "3dmake.toml"
    if not toml_file.exists():
        with open(proj_path / "3dmake.toml", 'w') as fh:
            fh.write("strict_warnings = true\n")

    # Create empty main.scad if none exists
    scad_path = proj_path / "src/main.scad"
    if not scad_path.exists():
        shutil.copy(
            ctx.config_dir / "templates" / "new_model.scad",
            scad_path,
        )

    stdout.write("Project created.\n")
    if proj_dir != '.':
        stdout.write(f'To enter the project directory, type "cd {proj_dir}".\n')
