import subprocess
import re
from typing import TextIO, Optional, List
from pathlib import Path

from .framework import Context, pipeline_action
from utils.bundle_paths import DEPS

@pipeline_action(gerund='slicing')
def slice(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    if not ctx.files.model.exists():
        raise RuntimeError("Model has not been built")

    PROFILES_DIR = ctx.config_dir / 'profiles'
    OVERLAYS_DIR = ctx.config_dir / 'overlays'

    profile = ctx.options.printer_profile
    ini_files: List[Path] = [PROFILES_DIR / f"{profile}.ini"]
    for overlay in ctx.options.overlays:
        # If there is a printer-specific version of this overlay, prefer it. Otherwise
        # use the default version
        profile_specific_path =  OVERLAYS_DIR / profile / f"{overlay}.ini"
        default_path = OVERLAYS_DIR / "default" / f"{overlay}.ini"
        if profile_specific_path.exists():
            ini_files.append(profile_specific_path)
        elif default_path.exists():
            ini_files.append(default_path)
        else:
            raise RuntimeError(f"Could not find overlay '{overlay}' for profile '{profile}'")

    project_prefix = ''
    if ctx.options.project_name:
        project_prefix = f"{ctx.options.project_name}-"
    gcode_file = ctx.files.build_dir / f"{project_prefix}{ctx.files.model_to_slice().stem}.gcode"
    
    cmd = [
        DEPS.SLICER,
        '--export-gcode',
        '-o', gcode_file,
        '--loglevel=1', # Log only errors
        '--scale', str(ctx.options.scale),
        ctx.files.model_to_slice()
    ]
    for ini_file in ini_files:
        cmd.append('--load')
        cmd.append(ini_file)

    # Here we suppress a lot of the progress messages from PrusaSlicer because
    # the loglevel directive doesn't seem to work. True errors should appear on
    # stderr where they will be displayed.
    process_result = subprocess.run(cmd, stdout=debug_stdout, stderr=stdout)
    if process_result.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {process_result.returncode}")

    ctx.files.sliced_gcode = gcode_file

    time_str = extract_time_estimates(ctx.files.sliced_gcode)
    if time_str:
        stdout.write(f"Estimated print time: {time_str}\n")

def extract_time_estimates(gcode_file: Path) -> Optional[str]:
    """
    Tries to parse out the print time estimate comment PrusaSlicer will leave in the GCode file,
    and converts it to a slightly nicer format for being read aloud.
    """
    if not gcode_file.exists():
        return

    pattern = re.compile(r'.*; estimated printing time .*? = (.+)$')
    
    with open(gcode_file, 'r') as fh:
        for line in fh:
            match_res = pattern.match(line)
            if match_res:
                time_str = match_res.group(1).upper()
                # The time string in the GCode is formatted by the function get_time_dhms
                # and will look like "10d 9h 8m 7s", but most users will be using a screen
                # reader so we might as well replace these with words.

                # We have converted time_str to uppercase specifically to prevent
                # our replacements from being mangled by later replacements (e.g.
                # the s in days being converted to "day seconds").
                time_str = time_str.replace('D', ' days')
                time_str = time_str.replace('H', ' hours')
                time_str = time_str.replace('M', ' minutes')
                time_str = time_str.replace('S', ' seconds')

                # Now we make it even cleaner by fixing up "1 days" and the like
                time_str = re.sub(r'\b1 days', '1 day', time_str)
                time_str = re.sub(r'\b1 hours', '1 hour', time_str)
                time_str = re.sub(r'\b1 minutes', '1 minute', time_str)
                time_str = re.sub(r'\b1 seconds', '1 second', time_str)

                return time_str

