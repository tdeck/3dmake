import subprocess
import re
from typing import TextIO, Optional, List
from pathlib import Path

from .framework import Context, pipeline_action
from utils.bundle_paths import DEPS

@pipeline_action(gerund='slicing')
def slice(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Slice the model and produce a printable gcode file '''
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

    slicer_keys = extract_slicer_keys(gcode_file)

    time_str = (
        slicer_keys.get('estimated printing time (normal mode)')
        or slicer_keys.get('estimated printing time (silent mode)')
    )
    if time_str:
        stdout.write(f"Estimated print time: {reformat_gcode_time(time_str)}\n")

    filament_used_str = slicer_keys.get('filament used [mm]')
    if filament_used_str:
        stdout.write(f"Filament used: {format_mm_length(filament_used_str)}\n")

def extract_slicer_keys(gcode_file: Path) -> dict[str, str]:
    results = {}
    with open(gcode_file, 'r') as fh:
        # First skip lines until we get to the objects_info line, which seems to be the first config
        # written by the slicer
        at_config = False
        for line in fh:
            if at_config or line.startswith('; objects_info ='):
                at_config = True
                parts = line.split(' = ', 1)
                if len(parts) > 1:
                    results[parts[0].lstrip(' ;')] = parts[1].rstrip('\r\n')
    return results

def reformat_gcode_time(time_str: str) -> str:
    # The time string in the GCode is formatted by the function get_time_dhms
    # and will look like "10d 9h 8m 7s", but most users will be using a screen
    # reader so we might as well replace these with words.

    time_str = time_str.upper()
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

def format_mm_length(length_str: str) -> str:
    mm = int(float(length_str))
    if mm > 1000:
        return f"about {mm / 1000:.2f} meters"
    elif mm > 10:
        return f"about {mm / 10:.1f} centimeters"
    else:
        return f"{mm} millimeters"
