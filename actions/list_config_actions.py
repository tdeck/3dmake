from typing import Optional

from .framework import Context, isolated_action
import utils.print_config as print_config
from utils.output_streams import OutputStream

@isolated_action(needs_options=True)
def list_profiles(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Lists available printer profiles '''
    print("Available printer profiles:")
    for profile_name in print_config.list_printer_profiles(ctx.config_dir):
        print(profile_name)
    print()

@isolated_action(needs_options=True)
def list_overlays(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Lists available slicer setting overlays '''
    print("Available overlays:")
    for overlay in print_config.list_overlays(ctx.config_dir):
        if overlay.profile:
            print(f"{overlay.name} (for profile {overlay.profile})")
        else:
            print(overlay.name)
    print()
