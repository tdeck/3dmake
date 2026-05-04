from typing import Optional
import shutil

from .framework import Context, isolated_action
import utils.print_config as print_config
from utils.output_streams import OutputStream
from utils.user_prompts import yes_or_no

@isolated_action(needs_options=True, input_file_type='.ini')
def install_profile(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Installs a new printer profile .INI file '''
    if not ctx.files.explicit_input_file:
        raise RuntimeError(f"You must specify a profile .ini file.")
    dest_file = ctx.config_dir / 'profiles' / ctx.files.explicit_input_file.name
    if dest_file.exists:
        if not yes_or_no(f'A profile called {dest_file.name} already exists. Overwrite it?'):
            return

    shutil.copy2(ctx.files.explicit_input_file, dest_file)
    stdout.writeln('Profile installed.')
