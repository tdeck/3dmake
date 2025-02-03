import textwrap
from typing import TextIO

from .framework import Context, isolated_action
from version import VERSION
from utils.bundle_paths import SCRIPT_DIR, SCRIPT_BIN_PATH

@isolated_action
def version(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    stdout.write(f"3Dmake version {VERSION}\n")
    stdout.write(f"Program location: {SCRIPT_BIN_PATH}\n")
    stdout.write(f"Configuration dir: {ctx.config_dir}\n")
    stdout.write("Created by Troy Deck\n")
    stdout.write("\nThanks for trying 3Dmake!\n")
