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

from prompt_toolkit import prompt
from platformdirs import user_config_path

from version import VERSION
from coretypes import FileSet, CommandOptions
from utils.editor import choose_editor
from utils.prompts import yes_or_no
from utils.stream_wrappers import IndentStream, FilterPipe
from utils.bundle_paths import DEPS
from utils.openscad import should_print_openscad_log
import actions

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

IMPLIED_VERBS = {}
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
        actions.help(None)
        parser.exit()

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

if actions.version.name in verbs:
    actions.version(context)
    sys.exit(0)

if actions.help.name in verbs:
    actions.help(None)
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

if actions.slice.name in verbs:
    actions.slice(context)

if actions.print.name in verbs:
    actions.print(context)

if infiles:
    # If we're in single file mode, copy the last result to the working dir
    output = file_set.final_output()
    if output:
        shutil.copy(file_set.final_output(), Path('.'))
        print(f"Result is {file_set.final_output().name}")

print("Done.")
