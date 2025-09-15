import subprocess
import platform
import os
from pathlib import Path

from coretypes import CommandOptions

def launch_editor(options: CommandOptions, file: Path, blocking: bool = False) -> None:
    """Launch the configured editor to edit a file"""
    background = options.edit_in_background
    editor = options.editor

    if not editor:
        if platform.system() == 'Windows':
            # If you change this, change the defaults populated in setup_action also
            editor = 'notepad'
            background = True
        else:
            # nano is an arbitrary fallback that we might improve in the future
            editor = os.getenv('VISUAL') or os.getenv('EDITOR') or 'nano'

    # Use shell=True to handle editor commands with arguments
    cmd = f'{editor} "{file}"'

    if background and not blocking:
        subprocess.Popen(cmd, shell=True)
    else:
        subprocess.run(cmd, shell=True)