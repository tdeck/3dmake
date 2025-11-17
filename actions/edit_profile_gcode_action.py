import tempfile
from pathlib import Path
from typing import TextIO

from .framework import Context, isolated_action
from utils.print_config import read_config_values, list_printer_profiles
from utils.prompts import option_select
from utils.editor import launch_editor

EXCLUDED_SETTINGS = {'binary_gcode'}  # These aren't actually gcode

def unescape_gcode(escaped_gcode: str) -> str:
    """Convert escaped GCODE string to multi-line format for editing"""
    if not escaped_gcode:
        return ""

    # Replace literal \n with actual newlines
    unescaped = escaped_gcode.replace('\\n', '\n')

    # Handle other common escapes
    unescaped = unescaped.replace('\\t', '\t')
    unescaped = unescaped.replace('\\"', '"')
    unescaped = unescaped.replace("\\'", "'")

    return unescaped

def escape_gcode(multiline_gcode: str) -> str:
    """Convert multi-line GCODE to escaped format for INI files"""
    if not multiline_gcode:
        return ""

    # Strip trailing whitespace and ensure consistent line endings
    cleaned = multiline_gcode.strip()

    # Escape characters that need escaping
    escaped = cleaned.replace('"', '\\"')
    escaped = escaped.replace("'", "\\'")
    escaped = escaped.replace('\t', '\\t')

    # Convert newlines to literal \n
    escaped = escaped.replace('\n', '\\n')

    return escaped

def update_profile_gcode_value(profile_path: Path, key: str, new_gcode: str) -> None:
    """Update a single GCODE value in a profile file"""
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile file not found: {profile_path}")

    # Read all lines
    with open(profile_path, 'r', encoding='utf-8') as fh:
        lines = fh.readlines()

    # Find and update the line
    escaped_value = escape_gcode(new_gcode)
    updated = False

    for i, line in enumerate(lines):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('#') or trimmed.startswith(';'):
            continue

        if '=' not in trimmed:
            continue

        line_key, _ = trimmed.split('=', 1)
        line_key = line_key.strip()

        if line_key == key:
            lines[i] = f"{key} = {escaped_value}\n"
            updated = True
            break

    if not updated:
        # Key not found, append it
        lines.append(f"{key} = {escaped_value}\n")

    # Write back
    with open(profile_path, 'w', encoding='utf-8') as fh:
        fh.writelines(lines)

@isolated_action(needs_options=True)
def edit_profile_gcode(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    """Edit GCODE scripts in printer profile (affected by -p)"""

    # Check that the printer profile exists
    profiles = list_printer_profiles(ctx.config_dir)
    if ctx.options.printer_profile not in profiles:
        raise RuntimeError(f"Printer profile '{ctx.options.printer_profile}' does not exist.")

    profile_path = ctx.config_dir / "profiles" / f"{ctx.options.printer_profile}.ini"

    # Read all config values from the profile
    config_values = read_config_values([profile_path])

    # Find all keys ending with "_gcode" but exclude non-GCODE settings
    gcode_keys = [key for key in config_values.keys()
                  if key.endswith('_gcode') and key not in EXCLUDED_SETTINGS]

    if not gcode_keys:
        stdout.write("No GCODE settings found in this profile.\n")
        return

    # Sort keys for consistent ordering
    gcode_keys.sort()

    # Present options to user
    stdout.write(f"GCODE settings in profile '{ctx.options.printer_profile}':\n\n")

    options = [(key, key) for key in gcode_keys]
    selected_key = option_select("Choose a GCODE setting to edit", options)

    # Get current value and unescape it
    current_escaped = config_values.get(selected_key, "")
    current_unescaped = unescape_gcode(current_escaped)

    # Create temporary file for editing
    # We must close the file and manually clean it up to work around the way
    # Windows locks open files
    temp_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.gcode', encoding='utf-8', delete=False)
    try:
        temp_file.write(current_unescaped)
        temp_file.close()
        temp_path = Path(temp_file.name)

        # Launch editor
        stdout.write(f"Opening {selected_key} for editing...\n")
        launch_editor(ctx.options, temp_path, blocking=True)

        # Read back the edited content
        with open(temp_path, 'r', encoding='utf-8') as fh: # TODO is this correct?
            edited_content = fh.read()

        # Update the profile file
        update_profile_gcode_value(profile_path, selected_key, edited_content)

        stdout.write(f"Updated {selected_key} in profile '{ctx.options.printer_profile}'\n")
    finally:
        pass # TODO temp_path.unlink()
