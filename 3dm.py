#! /usr/bin/env python3

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Literal, Union, Dict, Any, Callable
import argparse
import os
import sys
import tempfile
import tomllib
import shutil

from packaging.version import Version
from platformdirs import user_config_path

import actions.help_action
from version import VERSION
from coretypes import FileSet, CommandOptions
from utils.prompts import yes_or_no, prompt
from actions import ALL_ACTIONS_IN_ORDER, Context

CONFIG_DIR = Path(os.environ['3DMAKE_CONFIG_DIR']) if '3DMAKE_CONFIG_DIR' in os.environ else user_config_path('3dmake', None)
PROFILES_DIR = CONFIG_DIR / 'profiles'
OVERLAYS_DIR = CONFIG_DIR / 'overlays'

def error_out(message: str):
    print(message)
    sys.exit(1)

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
    elif Path('../3dmake.toml').exists():
        print("Using 3DMake project in parent directory...")
        with open("../3dmake.toml", 'rb') as fh:
            settings_dict.update(tomllib.load(fh))
        project_root = Path('..').resolve()

    if project_root and 'project_name' not in settings_dict:
        settings_dict['project_name'] = project_root.parts[-1]

    # Force library names to be lowercase to avoid confusing case issues
    if 'libraries' in settings_dict:
        settings_dict['libraries'] = [k.lower() for k in settings_dict['libraries']]

    return CommandOptions(**settings_dict), project_root

class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        actions.help_action.help(None)
        parser.exit()

parser = argparse.ArgumentParser(
    prog='3dmake',
    add_help=False,
)

parser.add_argument('-s', '--scale') # can be either "auto" or a float
parser.add_argument('-m', '--model')
parser.add_argument('-v', '--view', type=str)
parser.add_argument('-p', '--profile', type=str)
parser.add_argument('-o', '--overlay', action='extend', nargs=1)
parser.add_argument('-a', '--angle', action="extend", nargs=1)
parser.add_argument('-i', '--interactive', action='store_true')
parser.add_argument('-c', '--copies', type=int, default=1)
parser.add_argument('--colorscheme', type=str)
parser.add_argument('--image-size', type=str)
parser.add_argument('--help', '-h', action=HelpAction, nargs=0)
parser.add_argument('--debug', action='store_true')
parser.add_argument('actions_and_files', nargs='+')

# We follow this strategy of using parse_known_args() rather than parse_args()
# so that we can interleave actions_and_files with dashed options
args, unknown_args = parser.parse_known_args()
unknown_dashed_args = [e for e in unknown_args if e.startswith('-')]

if unknown_dashed_args:
    error_out(f"Unknown option(s): {' '.join(unknown_dashed_args)}")
args

extras = args.actions_and_files + unknown_args
infiles = []
while extras and '.' in extras[-1]:
    infiles.append(extras.pop())

verbs = set([x.lower() for x in extras])

if not len(verbs):
    error_out("Must provide an action verb")

# Check that 3dmake has been set up on this machine; if not do so
if not CONFIG_DIR.exists() and verbs != {'setup'}:
    print("3DMake settings and print options have not been set up on this machine.")
    if not yes_or_no("Do you want to set them up now?"):
        sys.exit(0)

    verbs = {'setup'}
    infiles = []


# Check verbs and insert any implied ones (recursively)
def add_implied_actions(verb_name, mutable_verbs_set):
    action = ALL_ACTIONS_IN_ORDER.get(verb_name)
    if action:
        for dependency in action.implied_actions:
            if dependency not in mutable_verbs_set:
                mutable_verbs_set.add(dependency)
                add_implied_actions(dependency, mutable_verbs_set)

verb_count = len(verbs)
should_load_options = False
needs_project_files = False
for verb in list(verbs):
    action = ALL_ACTIONS_IN_ORDER.get(verb)

    if not action or action.internal:
        raise error_out(f"Unknown action '{verb}'")

    if action.isolated and verb_count > 1:
        raise error_out(f"The action '{verb}' can only be used on its own")

    if action.needs_options:
        should_load_options = True
    if action.uses_project_files:
        needs_project_files = True

    # Add implied actions recursively
    add_implied_actions(verb, verbs)

# Validate last_in_chain constraints
action_names_in_order = list(ALL_ACTIONS_IN_ORDER.keys())
requested_actions_in_order = [name for name in action_names_in_order if name in verbs]

for i, action_name in enumerate(requested_actions_in_order):
    action = ALL_ACTIONS_IN_ORDER[action_name]
    if action.last_in_chain:
        # Check if there are any later actions in the internal ordering
        later_actions = requested_actions_in_order[i+1:]
        if later_actions:
            error_out(f"Action '{action_name}' cannot be followed by other actions. Found: {', '.join(later_actions)}")

# Load options if necessary
options, project_root, file_set = None, None, None
if should_load_options:
    options, project_root = load_config()

    # Check minimum version requirement if specified in project config
    if options.min_3dmake_version and project_root:
        current_version = Version(VERSION)
        min_required_version = Version(str(options.min_3dmake_version)) # Str in case they put a float in

        if current_version < min_required_version:
            error_out(f"This project requires 3DMake version {options.min_3dmake_version} or newer. "
                     f"Current version is {VERSION}. Please update 3DMake to continue.")

    if args.scale: # TODO support x,y,z scaling
        if args.scale.replace('.', '').isdecimal():
            options.scale = float(args.scale)
        elif args.scale.lower() == 'auto':
            options.scale = 'auto'
        else:
            raise error_out("Invalid value for --scale, must be a decimal number or auto")

    if args.model:
        if infiles:
            raise error_out("Cannot select a model name when using an input file")

        mod_name = args.model

        # Help the user out if they accidentally put in a filename
        if mod_name.lower().endswith('.scad'):
            mod_name = mod_name[:-5]
        options.model_name = mod_name

    if args.view:
        options.view = args.view

    if args.profile:
        options.printer_profile = args.profile

    if args.overlay:
        options.overlays = args.overlay

    if args.angle:
        options.image_angles = args.angle

    if args.colorscheme:
        options.colorscheme = args.colorscheme

    if args.image_size:
        options.image_size = args.image_size

    if args.copies:
        options.copies = args.copies

    if args.interactive:
        options.interactive = True

    if args.debug:
        options.debug = True

    if options.scale == 'auto':
        error_out("Auto-scaling is not supported yet") # TODO

    file_set = FileSet(options, project_root)

if len(infiles) > 1:
    error_out("Multiple inputs not supported yet")
elif infiles:
    if not needs_project_files:
        error_out("This action does not take an input file")

    single_infile = Path(infiles[0])
    extension = single_infile.suffix.lower()

    options.model_name = single_infile.stem # Derive the model name from the STL/scad name

    file_set.build_dir = Path(tempfile.mkdtemp())

    if extension == '.stl':
        file_set.scad_source = None
        file_set.model = single_infile
    elif extension == '.scad':
        file_set.scad_source = single_infile
        file_set.model = file_set.build_dir / f"{options.model_name}.stl"
        # TODO is this auto-add behavior a good idea?
        verbs.add('build')
    else:
        error_out("Unsupported file formats. Supported formats are .stl and .scad")
elif not needs_project_files:
    pass # Skip setting up the project root since we shouldn't need it
elif project_root:
    file_set.scad_source = project_root / "src" / f"{options.model_name}.scad"
else:
    raise error_out("Must either specify input file or run in a 3DMake project directory")

context = Context(
    config_dir=CONFIG_DIR,
    options=options,
    files=file_set,
    explicit_overlay_arg=args.overlay,
    single_file_mode=bool(infiles),
)

for name, action in ALL_ACTIONS_IN_ORDER.items():
    if name in verbs:
        try:
            action(context)
        except Exception as e:
            if options and options.debug:
                raise
            else:
                error_out("ERORR: " + str(e))
        except KeyboardInterrupt as e:
            print("Exited.")
            sys.exit(2)
        if action.isolated:
            sys.exit(0) # So we don't print Done.

if infiles:
    # If we're in single file mode, copy the last result to the working dir
    outputs = file_set.final_outputs()
    if outputs:
        for file in outputs:
            shutil.copy(file, Path('.'))

        if len(outputs) == 1:
            print(f"Result is in {outputs[0].name}")
        else:
            print(f"Result files:")
            for file in outputs:
                print(f"    {file.name}")

print("Done.")
