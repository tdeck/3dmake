#! /usr/bin/env python3

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Literal, Union, Dict, Any, Callable
import argparse
import os
import sys
import subprocess
import tempfile
import tomllib
import shutil
import json
import re
import textwrap

from prompt_toolkit import prompt
from platformdirs import user_config_path
import requests

from version import VERSION
from coretypes import FileSet, CommandOptions
from utils.editor import choose_editor
from utils.prompts import yes_or_no
from utils.stream_wrappers import IndentStream, FilterPipe
from utils.bundle_paths import SCRIPT_DIR, SCRIPT_BIN_PATH, DEPS
from utils.openscad import should_print_openscad_log
import actions

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

CONFIGLESS_VERBS = {
    'setup',
    'new',
    'version',
    'help',
}

INPUTLESS_VERBS = CONFIGLESS_VERBS | {
    'edit-model',
    'edit-profile',
    'edit-overlay',
    'edit-global-config',
}

ISOLATED_VERBS = INPUTLESS_VERBS

SUPPORTED_VERBS = {
    'info',
    'build',
    'orient',
    'preview',
    'slice',
    'print',
} | ISOLATED_VERBS

IMPLIED_VERBS = {
    # Dollar-sign verbs are internal steps that may not print an output
    'print': 'slice',
}
for action_name, action in actions.ALL_ACTIONS.items():
    assert len(action.implied_actions) <= 1  # TODO make multiple deps work later
    for dep in action.implied_actions:
        IMPLIED_VERBS[action_name] = dep

CONFIG_DIR = user_config_path('3dmake', None)
PROFILES_DIR = CONFIG_DIR / 'profiles'
OVERLAYS_DIR = CONFIG_DIR / 'overlays'

def load_config() -> Tuple[CommandOptions, Optional[Path]]:
    """ Returns merged options, project root """
    project_root = None

    # First load the global defaults
    with open(CONFIG_DIR / "defaults.toml", 'rb') as fh:
        settings_dict = tomllib.load(fh)

    # TODO should we check parent dirs?
    if Path('./3dmake.toml').exists():
        with open("./3dmake.toml", 'rb') as fh:
            settings_dict.update(tomllib.load(fh))
        project_root = Path().absolute()

        if 'project_name' not in settings_dict:
            settings_dict['project_name'] = project_root.parts[-1]

    return CommandOptions(**settings_dict), project_root

class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        self.print_help()
        parser.exit()

    @staticmethod
    def print_help():
        print(textwrap.dedent('''\
            Usage: 3dm ACTIONS... [OPTIONS]... [INPUT_FILE]

            Examples:
                3dm build
                3dm build orient slice
                3dm build orient slice --model cover --overlay supports
                3dm info alpaca.stl
                3dm preview alpaca.stl
                3dm slice print alpaca.stl

            Actions:
                setup               Set up 3dmake for the first time, or overwrite existing settings
                new                 Create a new 3dmake project directory structure
                build               Build the OpenSCAD model and produce an STL file
                info                Get basic dimensional info about the model, and AI description if enabled
                orient              Auto-orient the model to minimize support
                preview             Produce a 2-D representation of the object
                slice               Slice the model and produce a printable gcode file
                print               Send the sliced model to OctoPrint
                edit-model          Open model SCAD file in your editor (affected by -m)
                edit-overlay        Open an overlay file in your editor (affected by -o)
                edit-profile        Open printer profile in your editor (affected by -p)
                edit-global-config  Edit 3DMake user settings file (default printer, API keys, etc...)
                help                Display this message
                version             Print the 3dmake version and paths

            Options:
                --scale 1.0     Scale by a decimal factor
                --model NAME    Choose a model in a multi-model project
                --profile NAME  Select a printer profile
                --overlay NAME  Apply an overlay to slicer settings; can be used multiple times
                --view NAME     The type of preivew to produce, see the documentation for more info

            Each option can be abbreviated as one letter with a single dash (e.g. -s 50% to scale)
        '''))

parser = argparse.ArgumentParser(
    prog='3dmake',
    add_help=False,
)

parser.add_argument('-s', '--scale') # can be either "auto" or a float
parser.add_argument('-m', '--model')
parser.add_argument('-v', '--view', type=str)
parser.add_argument('-p', '--profile', type=str)
parser.add_argument('-o', '--overlay', action='extend', nargs='*')
parser.add_argument('--help', '-h', action=HelpAction, nargs=0)
parser.add_argument('--debug', action='store_true')
parser.add_argument('actions_and_files', nargs='+')

args = parser.parse_args()

extras = args.actions_and_files
infiles = []
while extras and '.' in extras[-1]:
    infiles.append(extras.pop())

verbs = set([x.lower() for x in extras])

if not len(verbs):
    raise RuntimeError("Must provide an action verb")

# Check that 3dmake has been set up on this machine; if not do so
if not CONFIG_DIR.exists() and verbs != {'setup'}:
    print("3DMake settings and print options have not been set up on this machine.")
    if not yes_or_no("Do you want to set them up now?"):
        sys.exit(0)

    verbs = {'setup'}
    infiles = []


# Check verbs and insert any implied ones
for verb in list(verbs):
    if verb not in SUPPORTED_VERBS:
        raise RuntimeError(f"Unknown action '{verb}'")
    if verb in ISOLATED_VERBS and len(verbs) > 1:
        raise RuntimeError(f"The action '{verb}' can only be used on its own'")
    if verb in IMPLIED_VERBS:
        verbs.add(IMPLIED_VERBS[verb])

# Load options if necessary
options, project_root = None, None
if next(iter(verbs)) not in CONFIGLESS_VERBS:
    options, project_root = load_config()

if args.scale: # TODO support x,y,z scaling
    if args.scale.replace('.', '').isdecimal():
        options.scale = float(args.scale)
    elif args.scale.lower() == 'auto':
        options.scale = 'auto'
    else:
        raise RuntimeError("Invalid value for --scale, must be a decimal number or auto")

if args.model:
    options.model_name = args.model
    if infiles:
        raise RuntimeError("Cannot select a model name when using an input file")

if args.profile:
    options.printer_profile = args.profile

if args.view:
    options.view = args.view

if args.debug:
    options.debug = True

if options and options.scale == 'auto':
    raise NotImplementedError("Auto-scaling is not supported yet") # TODO

file_set = None
if options:
    file_set = FileSet(options)

if len(infiles) > 1:
    raise RuntimeError("Multiple inputs not supported yet")
elif next(iter(verbs)) in INPUTLESS_VERBS:
    if infiles:
        raise RuntimeError("This action does not take an input file")
    # Otherwise don't require an infile
elif infiles:
    single_infile = Path(infiles[0])
    extension = single_infile.suffix.lower()

    options.model_name = single_infile.stem # Derive the model name from the STL/scad name

    file_set.build_dir = Path(tempfile.mkdtemp())

    if extension == '.stl':
        file_set.model = single_infile
    elif extension == '.scad':
        file_set.scad_source = single_infile
        file_set.model = file_set.build_dir / f"{options.model_name}.stl"
        # TODO is this auto-add behavior a good idea?
        verbs.add('build')
    else:
        raise RuntimeError("Unsupported file formats. Supported formats are .stl and .scad")
elif project_root:
    file_set.scad_source = project_root / "src" / f"{options.model_name}.scad"
else:
    raise RuntimeError("Must either specify input file or run in a 3Dmake project directory")

if args.overlay:
    options.overlays = args.overlay

indent_stdout = IndentStream(sys.stdout)

if args.debug:
    # No filtering in debug mode
    filter_and_indent_stdout = indent_stdout
    debug_output = indent_stdout
else:
    filter_and_indent_stdout = FilterPipe(
        indent_stdout,
        filter_fn=should_print_openscad_log,
    )
    debug_output = subprocess.DEVNULL

context = actions.Context(
    config_dir=CONFIG_DIR,
    options=options,
    files=file_set,
    explicit_overlay_arg=args.overlay,
)

if actions.setup.name in verbs:
    actions.setup(context)
    sys.exit(0)

if verbs == {'new'}:
    proj_dir = prompt("Choose a project directory name (press ENTER for current dir): ").strip()
    if proj_dir == '':
        proj_dir = '.'  # Current directory

    proj_path = Path(proj_dir)

    # Create project dirs
    proj_path.mkdir(exist_ok=True)
    (proj_path / "src").mkdir(exist_ok=True)
    (proj_path / "build").mkdir(exist_ok=True)

    # Create empty 3dmake.toml if none exists
    toml_file = proj_path / "3dmake.toml"
    if not toml_file.exists():
        with open(proj_path / "3dmake.toml", 'w') as fh:
            fh.write("strict_warnings = true\n")

    # Create empty main.scad if none exists
    open(proj_path / "src/main.scad", 'a').close()

if verbs == {'version'}:
    print(f"3Dmake version {VERSION}")
    print(f"Program location: {SCRIPT_BIN_PATH}")
    print(f"Configuration dir: {CONFIG_DIR}")
    print("Created by Troy Deck")
    print("\nThanks for trying 3Dmake!")
    sys.exit(0)

if verbs == {'help'}:
    HelpAction.print_help()
    sys.exit(0)

if verbs == {'edit-model'}:
    actions.edit_model(context)
    sys.exit(0)

if verbs == {'edit-global-config'}:
    actions.edit_global_config(context)
    sys.exit(0)

if verbs == {'edit-profile'}:
    actions.edit_profile(context)
    sys.exit(0)

if verbs == {'edit-overlay'}:
    actions.edit_overlay(context)
    sys.exit(0)

if actions.build.name in verbs:
    actions.build(context)

if actions.orient.name in verbs:
    actions.orient(context)

if actions.measure_model.name in verbs:
    actions.measure_model(context)

if actions.info.name in verbs:
    actions.info(context)

if actions.preview.name in verbs:
    actions.preview(context)

if 'slice' in verbs:
    if not file_set.model.exists():
        raise RuntimeError("Model has not been built")

    print("\nSlicing...")

    ini_files: List[Path] = [PROFILES_DIR / f"{options.printer_profile}.ini"]
    for overlay in options.overlays:
        # If there is a printer-specific version of this overlay, prefer it. Otherwise
        # use the default version
        profile_specific_path =  OVERLAYS_DIR / options.printer_profile / f"{overlay}.ini"
        default_path = OVERLAYS_DIR / "default" / f"{overlay}.ini"
        if profile_specific_path.exists():
            ini_files.append(profile_specific_path)
        elif default_path.exists():
            ini_files.append(default_path)
        else:
            raise RuntimeError(f"Could not find overlay '{overlay}' for profile '{options.printer_profile}'")

    project_prefix = ''
    if options.project_name:
        project_prefix = f"{options.project_name}-"
    gcode_file = file_set.build_dir / f"{project_prefix}{file_set.model_to_slice().stem}.gcode"
    
    cmd = [
        DEPS.SLICER,
        '--export-gcode',
        '-o', gcode_file,
        '--loglevel=1', # Log only errors
        '--scale', str(options.scale),
        file_set.model_to_slice()
    ]
    for ini_file in ini_files:
        cmd.append('--load')
        cmd.append(ini_file)

    # Here we suppress a lot of the progress messages from PrusaSlicer because
    # the loglevel directive doesn't seem to work. True errors should appear on
    # stderr where they will be displayed.
    process_result = subprocess.run(cmd, stdout=debug_output, stderr=indent_stdout)
    if process_result.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {process_result.returncode}")

    file_set.sliced_gcode = gcode_file

    time_str = extract_time_estimates(file_set.sliced_gcode)
    if time_str:
        print(f"    Estimated print time: {time_str}")

if 'print' in verbs:
    print("\nPrinting...")
    server_filename = file_set.sliced_gcode.name
    with open(file_set.sliced_gcode, 'rb') as fh:
        response = requests.post(
            f"{options.octoprint_host}/api/files/local", # TODO folder
            headers={
                'X-Api-Key': options.octoprint_key,
            },
            files={
                'file': (server_filename, fh, 'application/octet-stream'),
            },
            data={
                'select': True,
                'print': options.auto_start_prints,
            },
            verify=False, # TODO; this is needed for self-signed local servers
        )

    # TODO handle this better
    if response.status_code == 201:
        print(f"    File uploaded successfully as {server_filename}!")
    else:
        print(f"    Failed to upload. Status code: {response.status_code}")
        print(response.text)

if infiles:
    # If we're in single file mode, copy the last result to the working dir
    output = file_set.final_output()
    if output:
        shutil.copy(file_set.final_output(), Path('.'))
        print(f"Result is {file_set.final_output().name}")

print("Done.")
