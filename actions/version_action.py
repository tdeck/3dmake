import textwrap

from .framework import Context, isolated_action
from utils.output_streams import OutputStream
from version import VERSION
from utils.bundle_paths import SCRIPT_DIR, SCRIPT_BIN_PATH

@isolated_action
def version(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Print the 3DMake version and paths '''

    stdout.writeln(f"3DMake version {VERSION}")
    stdout.writeln(f"Program location: {SCRIPT_BIN_PATH}")
    stdout.writeln(f"Configuration dir: {ctx.config_dir}")
    stdout.writeln("Created by Troy Deck")
    stdout.write("\nThanks for trying 3DMake!\n")
