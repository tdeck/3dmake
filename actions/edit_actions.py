import shutil
from pathlib import Path

from .framework import Context, isolated_action
from utils.print_config import list_printer_profiles, list_overlays, resolve_profile_path, OverlayName
from utils.user_prompts import yes_or_no, option_select, option_select_with_current, prompt
from utils.editor import launch_editor
from utils.llm_prompt import ensure_custom_prompt_exists
from utils.output_streams import OutputStream

@isolated_action(needs_options=True, uses_project_files=True)
def edit_model(ctx: Context, stdout: OutputStream, __):
    ''' Open model SCAD file in your editor (affected by -m) '''
    if not ctx.files.scad_source.exists():
        parent_dir = ctx.files.scad_source.parent
        if not parent_dir.is_dir():
            raise RuntimeError(
                f"The model directory {parent_dir} does not exist. \n"
                "This looks like an incorrectly formatted project."
            )

        # Some editors might not like being asked to open a file that does not
        # exist, so we just make one
        stdout.writeln("Model file does not exist; creating an empty model.")
        ctx.files.scad_source.touch()

    launch_editor(ctx.options, ctx.files.scad_source)

@isolated_action(needs_options=True)
def edit_global_config(ctx: Context, _, __):
    ''' Edit 3DMake user settings file (default printer, API keys, etc...) '''
    launch_editor(ctx.options, ctx.config_dir / "defaults.toml")

@isolated_action(needs_options=True)
def clone_profile(ctx: Context, stdout: OutputStream, __):
    ''' Clone an existing printer profile under a new name '''

    profiles = list_printer_profiles(ctx.config_dir)
    if not profiles:
        raise RuntimeError("No printer profiles found.")

    profile_options = [(p.replace('_', ' '), p) for p in profiles]
    source_profile = option_select_with_current("Choose a profile to clone", profile_options, ctx.options.printer_profile)

    new_name = prompt("Name for new profile: ").strip()
    if not new_name:
        raise RuntimeError("Profile name cannot be empty.")

    new_name_key = new_name.replace(' ', '_')
    dest_path = ctx.config_dir / "profiles" / f"{new_name_key}.ini"
    if dest_path.exists():
        raise RuntimeError(f"A profile named '{new_name_key}' already exists.")

    source_path = ctx.config_dir / "profiles" / f"{source_profile}.ini"
    shutil.copy(source_path, dest_path)
    stdout.writeln(f"Created profile '{new_name_key}'.")

    if yes_or_no("Open new profile in editor?"):
        launch_editor(ctx.options, dest_path)

@isolated_action(needs_options=True)
def edit_profile(ctx: Context, _, __):
    ''' Open printer profile in your editor (affected by -p) '''

    profile_path = resolve_profile_path(ctx.config_dir, ctx.options.printer_profile)
    if not profile_path.exists():
        # TODO offer to create a new one or copy one. Unfortunately this is a
        # little bit complicated
        raise RuntimeError(f"Printer profile '{ctx.options.printer_profile}' does not exist.")

    launch_editor(ctx.options, profile_path)

@isolated_action(needs_options=True)
def edit_overlay(ctx: Context, _, __):
    ''' Open an overlay file in your editor (affected by -o) '''

    existing_overlays = list_overlays(ctx.config_dir)

    overlay_file = None
    if ctx.explicit_overlay_arg and len(ctx.explicit_overlay_arg) == 1:
        overlay_name = ctx.explicit_overlay_arg[0]
    else:
        overlay_name = prompt("Which overlay? ").strip()

    matches = [o for o in existing_overlays if o.name == overlay_name]

    if len(matches) == 0:
        if not yes_or_no(f"No overlay called {overlay_name}, create one?"):
            return

        profile_name = None
        if yes_or_no("Limit this profile to a specific printer?"):
            profile_options = [
                (p.replace('_', ' '), p)
                for p in list_printer_profiles(ctx.config_dir)
            ]

            profile_name = option_select("Choose a printer", profile_options)

        overlay_file = OverlayName(name=overlay_name, profile=profile_name).path(ctx.config_dir)

        # Copy over template to create new file
        overlay_file.parent.mkdir(exist_ok=True)
        shutil.copy(ctx.config_dir / "templates" / "new_overlay.ini", overlay_file)

    elif len(matches) > 1:
        overlay_file = option_select(
            "Select an option",
            options=[
                (o.listing_name(), o.path(ctx.config_dir))
                for o in matches
            ]
        )
    else:
        overlay_file = matches[0].path(ctx.config_dir)

    launch_editor(ctx.options, overlay_file)

@isolated_action(needs_options=True)
def edit_prompt(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    """Edit the AI prompt used by the info command"""

    # Ensure the prompt file exists (creates with default if needed)
    prompt_file = ensure_custom_prompt_exists(ctx.config_dir)

    if not prompt_file.exists():
        stdout.writeln(f"Created new prompt file at {prompt_file}")
    else:
        stdout.writeln(f"Editing existing prompt file at {prompt_file}")

    launch_editor(ctx.options, prompt_file)
