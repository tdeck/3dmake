import subprocess
import platform
import os
from time import time
from pathlib import Path

from coretypes import CommandOptions

MIN_BLOCKING_SECONDS = 0.5

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

    # We make sure the path is resolved to an external path to work
    # around a weird bug on Windows, where the Python process will
    # see its own AppData/Local dir sanboxed to another location (but
    # where this won't happen to subprocesses we launch in the shell)
    # See this bug: https://github.com/python/cpython/issues/122057
    resolved_file = file.resolve(strict=False)

    # Use shell=True to handle editor commands with arguments
    cmd = f'{editor} "{resolved_file}"'

    if background and not blocking:
        subprocess.Popen(cmd, shell=True)
    else:
        start_time = time()
        subprocess.run(cmd, shell=True)
        elapsed = time() - start_time
        # In case we need a write->edit->read workflow and the editor
        # command doesn't actually block, we can detect that it ended
        # too early and ask the user to press a key when they finished.
        if blocking and elapsed < MIN_BLOCKING_SECONDS:
            input("Press ENTER when finished editing:")
