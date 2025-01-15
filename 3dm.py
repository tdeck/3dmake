#! /usr/bin/env python3


from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Literal, Union, Dict, Any, Callable
import argparse
import os
import sys
import subprocess
import tempfile
import threading
import tomllib
import platform
import shutil
import json

from prompt_toolkit import prompt
from platformdirs import user_config_path
import requests
import stl.mesh
from tweaker3 import MeshTweaker, FileHandler

from version import VERSION

if getattr(sys, 'frozen', False):
    # Special case for PyInstaller
    SCRIPT_DIR = Path(sys._MEIPASS)
    SCRIPT_BIN_PATH = Path(sys.executable).absolute()
else:
    SCRIPT_DIR = Path(sys.path[0])
    SCRIPT_BIN_PATH = Path(__file__).absolute()


@dataclass
class Dependencies:
    OPENSCAD: Path
    SLICER: Path

def get_deps() -> Dependencies:
    os_type = platform.system()

    openscad_path = SCRIPT_DIR.joinpath(
        {
            'Linux': 'deps/linux/OpenSCAD.AppImage',
            'Windows': 'deps/windows/openscad/openscad.exe',
        }[os_type]
    )

    slicer_path = SCRIPT_DIR.joinpath(
        {
            'Linux': 'deps/linux/PrusaSlicer.AppImage',
            'Windows': 'deps/windows/prusaslicer/prusa-slicer-console.exe',
        }[os_type]
    )


    return Dependencies(openscad_path, slicer_path)

def yes_or_no(question: str) -> bool:
    answer = prompt(f"{question} (y or n): ").strip()
    return answer == 'y'

def option_select(prompt_msg: str, options: Dict[str, Any], allow_none=False) -> Optional[Any]:
    while True:
        print(prompt_msg)
        index_to_opts: Dict[int, Any] = {}
        for i, (option_key, option_value) in enumerate(options.items()):
            index_to_opts[i + 1] = option_value
            print(f"{i + 1}: {option_key}")

        res = prompt("Choose an option number, or type AGAIN to re-print the list: ").strip()

        if allow_none and res == '':
            return None
        if res.isdigit() and int(res) in index_to_opts:
            return index_to_opts[int(res)]
        elif res.lower() == 'again':
            continue
        else:
            print("That is not a valid option")
            continue

def add_self_to_path():
    os_type = platform.system()

    if os_type == 'Windows':
        bin_dir = Path(os.getenv('USERPROFILE')) / "AppData" / "Local" / "Microsoft" / "WindowsApps"

        if bin_dir.exists():
            import mslex
            # Windows requires special admin permission to create symlinks
            # So instead we create a batch file in this directory that simply runs 3dmake
            with open(bin_dir / '3dm.bat', 'w') as fh:
                fh.write("@echo off\r\n")
                fh.write(f"{mslex.quote(str(SCRIPT_BIN_PATH))} %*\r\n")
        else:
            print("3dmake was not added to your PATH automatically. Consider adding this folder")
            print("to your PATH environment variable:")
            print(SCRIPT_BIN_PATH.parent)
            # TODO not sure whether to give a setx command or not, hopefully this is a rare case

    else:  # Assume a Linux/Unix platform
        bin_dir = Path(os.getenv('HOME')) / '.local' / 'bin' # This is in the XDG spec

        if bin_dir.exists():
            symlink_path = bin_dir / '3dm'
            symlink_path.unlink(missing_ok=True) # Replace if one already exists
            symlink_path.symlink_to(SCRIPT_BIN_PATH)
        else:
            # If it doesn't exist, maybe we could create it and it'll be in the PATH, but maybe
            # not. Better to assume it won't work and tell the user to set things up themselves.

            user_shell = os.getenv('SHELL', '')
            shell_config_file = '~/.profile'
            if 'bash' in user_shell:
                shell_config_file = '~/.bashrc'
            elif 'zsh' in user_shell:
                shell_config_file = '~/.zshrc'

            print("3dmake was not added to your PATH automatically. Consider adding a line like")
            print(f"this to your shell config file (e.g. {shell_config_file}):")
            print(f'export PATH="{SCRIPT_BIN_PATH.parent}:$PATH"')
            print(f"After doing this, you must reload your shell.")


INPUTLESS_VERBS = {
    'setup',
    'new',
    'version',
}

ISOLATED_VERBS = INPUTLESS_VERBS

SUPPORTED_VERBS = {
    'info',
    'build',
    'orient',
    'sketch',
    'slice',
    'print',
} | ISOLATED_VERBS

PROJECTION_CODE = {
    # These all receive the following vars:
    # stl_file, x_mid, y_mid, z_mid, x_size, y_size, z_size
    '3sil': '''
        HEIGHT = .6;
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        linear_extrude(HEIGHT) {
            translate([0, z_size + SPACING, 0]) projection() model();
            translate([-x_size - SPACING, 0, 0]) projection() rotate([-90, 90, 0]) model();
            projection() rotate([-90, 0, 0]) model();
        }
    '''
}

IMPLIED_VERBS = {
    'print': 'slice',
    'sketch': 'info',  # The sketch step needs model dimensions to arrange the model
}


DEPS = get_deps()

CONFIG_DIR = user_config_path('3dmake', None)
PROFILES_DIR = CONFIG_DIR / 'profiles'
OVERLAYS_DIR = CONFIG_DIR / 'overlays'

class IndentStream:
    def __init__(self, wrapped_stream, indent=4, filter_fn: Callable[[str], bool]=lambda _: True):
        self.wrapped_stream = wrapped_stream
        self.indent_str = ' ' * indent
        self.filter_fn = filter_fn
        self.pipe_read, self.pipe_write = os.pipe()

        # Start a thread to read from the pipe and forward indented output
        self._start_reader_thread()

    def _start_reader_thread(self):
        def _reader():
            with os.fdopen(self.pipe_read, 'r') as pipe:
                for line in pipe:
                    if self.filter_fn(line):
                        # Indent each line and write to the wrapped stream
                        self.wrapped_stream.write(f"{self.indent_str}{line}")
                    self.wrapped_stream.flush()

        threading.Thread(target=_reader, daemon=True).start()

    def fileno(self):
        return self.pipe_write

    def close(self):
        os.close(self.pipe_write)


@dataclass(kw_only=True)
class CommandOptions:
    project_name: Optional[str] = None # This will be populated automatically with the project's parent dir if not overridden
    model_name: str = "main"
    sketch_view: str
    printer_profile: str
    scale: Union[float, Literal["auto"]] = 1.0
    overlays: List[str] = field(default_factory=list)
    octoprint_host: Optional[str] = None
    octoprint_key: Optional[str] = None
    auto_start_prints: bool = False
    debug: bool = False

class FileSet:
    def __init__(self, options: CommandOptions):
        self.build_dir: Path = Path('build') # TODO based on options

        self.scad_source = Path("src") / f"{options.model_name}.scad"
        self.model = self.build_dir / f"{options.model_name}.stl"

    build_dir: Path
    scad_source: Optional[Path]
    model: Optional[Path]
    oriented_model: Optional[Path] = None
    projected_model: Optional[Path] = None
    sliced_gcode: Optional[Path] = None

    def model_to_project(self) -> Optional[Path]:
        return self.oriented_model or self.model

    def model_to_slice(self) -> Optional[Path]:
        return self.projected_model or self.oriented_model or self.model

    def final_output(self) -> Optional[Path]:
        """ Returns the most processed output file; which will be the command's final result in single file mode. """
        return self.sliced_gcode or self.model_to_slice()


@dataclass
class Thruple:
    x: float
    y: float
    z: float

@dataclass
class MeshMetrics:
    xrange: Tuple[float, float]
    yrange: Tuple[float, float]
    zrange: Tuple[float, float]

    def sizes(self) -> Thruple:
        return Thruple(
            self.xrange[1] - self.xrange[0],
            self.yrange[1] - self.yrange[0],
            self.zrange[1] - self.zrange[0]
        )

    def midpoints(self) -> Thruple:
        return Thruple(
            (self.xrange[1] + self.xrange[0]) / 2,
            (self.yrange[1] + self.yrange[0]) / 2,
            (self.zrange[1] + self.zrange[0]) / 2,
        )


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


def should_print_openscad_log(line: str) -> bool:
    """
    Returns true if the log line matches an ERROR, WARNING, or TRACE pattern.

    OpenSCAD doesn't provide a good way to filter logs on the command line so we must resort to this.
    """

    ALLOWED_PREFIXES = [ # From printutils.cc, some of these may never appear
        'ERROR:',
        'WARNING:',
        'TRACE:',
        'FONT-WARNING:',
        'EXPORT-WARNING:',
        'EXPORT-ERROR:',
        'PARSER-ERROR:',
        'ECHO:', # Logs from within OpenSCAD code; this will need better handling for multi-line echos
    ]

    # This may be inefficient but the number of log lines should be low
    for prefix in ALLOWED_PREFIXES:
        if line.startswith(prefix):
            return True

    return False

parser = argparse.ArgumentParser(
    prog='3dmake',
)

parser.add_argument('-s', '--scale') # can be either "auto" or a float
parser.add_argument('-m', '--model')
parser.add_argument('-p', '--profile', type=str)
parser.add_argument('-o', '--overlay', action='extend', nargs='*')
parser.add_argument('--debug', action='store_true')
parser.add_argument('extra', nargs='+')

args = parser.parse_args()

extras = args.extra
infiles = []
while extras and '.' in extras[-1]:
    infiles.append(extras.pop())

verbs = set([x.lower() for x in extras])

if not len(verbs):
    raise RuntimeError("Must provide a verb")

# Check that 3dmake has been set up on this machine; if not do so
if not CONFIG_DIR.exists() and verbs != {'setup'}:
    print("3DMake settings and print options have not been set up on this machine.")
    if not yes_or_no("Do you want to set them up now?"):
        exit(0)

    verbs = {'setup'}
    infiles = []


# Check verbs and insert any implied ones
for verb in list(verbs):
    if verb not in SUPPORTED_VERBS:
        raise RuntimeError(f"Unknown verb '{verb}'")
    if verb in ISOLATED_VERBS and len(verbs) > 1:
        raise RuntimeError(f"The verb '{verb}' can only be used on its own'")
    if verb in IMPLIED_VERBS:
        verbs.add(IMPLIED_VERBS[verb])

# Load options if necessary
options, project_root = None, None
if next(iter(verbs)) not in INPUTLESS_VERBS:
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

if args.debug:
    options.debug = True

if options and options.scale == 'auto':
    raise NotImplementedError("Auto-scaling is not supported yet") # TODO

if options:
    file_set = FileSet(options)

if len(infiles) > 1:
    raise RuntimeError("Multiple inputs not supported yet")
elif next(iter(verbs)) in INPUTLESS_VERBS:
    if infiles:
        raise RuntimeError("This verb does not take an input file")
    # Otherwise don't require an infile
elif infiles:
    single_infile = Path(infiles[0])
    extension = single_infile.suffix.lower()

    options.model_name = single_infile.stem # Derive the model name from the STL/scad name

    file_set.build_dir = Path(tempfile.mkdtemp())
    print("Build dir:", file_set.build_dir) # TODO

    if extension == '.stl':
        file_set.model = single_infile
    elif extension == '.scad':
        file_set.scad_source = single_infile
        file_set.model = file_set.build_dir / "model.stl"
        # TODO is this auto-add behavior a good idea?
        verbs.add('build')
    else:
        raise RuntimeError("Unsupported file formats. Supported formats are .stl and .scad")
elif project_root:
    file_set.scad_source = project_root / "src" / f"{options.model_name}.scad"
else:
    raise RuntimeError("Must either specify input file or run in a 3dmake project directory")

if args.overlay:
    options.overlays = args.overlay

indent_stdout = IndentStream(sys.stdout)

if args.debug:
    # No filtering in debug mode
    filter_and_indent_stdout = indent_stdout
    debug_output = indent_stdout
else:
    filter_and_indent_stdout = IndentStream(
        sys.stdout,
        filter_fn=should_print_openscad_log,
    )
    debug_output = subprocess.DEVNULL

if verbs == {'setup'}:
    if CONFIG_DIR.exists():
        print(f"The configuration directory {CONFIG_DIR} already exists.")
        print(f"I can overwrite the configuration files and printer profiles that came")
        print(f"with 3dmake, returning them to default settings.")
        if not yes_or_no("Do you want to do this?"):
            print("Cancelling.")
            exit(0)

    default_conf_dir = SCRIPT_DIR / 'default_config'
    shutil.copytree(default_conf_dir, CONFIG_DIR, dirs_exist_ok=True) # Don't need to mkdir -p as shutil will do this

    settings_dict = dict(
        sketch_view='3sil',
        model_name='main',
        auto_start_prints=True,
    )


    profile_names = [
        file_name[:-4] # Strip extension
        for file_name in os.listdir(CONFIG_DIR / "profiles")
            if file_name.endswith(".ini")  # Filter for INI files
    ]

    profile_options = {
        p.replace('_', ' '): p
        for p in profile_names
    }

    profile_name = option_select("Choose a supported printer model", profile_options)
    settings_dict['printer_profile'] = profile_name

    if yes_or_no("Do you want to set up an OctoPrint connection?"):
        server = prompt("What is the web address of your OctoPrint server (including http://)? ").strip()

        print("You must set up an OctoPrint API key for 3dmake if you do not have one already.")
        print("To do this, open the OctoPrint settings in your browser, navigate to Application Keys,")
        print("and manually generate a key.")

        key = prompt("What is your OctoPrint application key? ").strip()

        settings_dict['octoprint_server'] = server
        settings_dict['octoprint_key'] = key
    

    with open(CONFIG_DIR / "defaults.toml", 'w') as fh:
        # TODO write this properly; it's brittle
        for k, v in settings_dict.items():
            fh.write(f"{k} = {json.dumps(v)}\n")
        
    add_self_to_path()

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
    open(proj_path / "3dmake.toml", 'a').close()

    # Create empty main.scad if none exists
    open(proj_path / "src/main.scad", 'a').close()

if verbs == {'version'}:
    print(f"3Dmake version {VERSION}")
    print(f"Program location: {SCRIPT_BIN_PATH}")
    print(f"Configuration dir: {CONFIG_DIR}")
    print("\nThanks for trying 3Dmake!")

if 'build' in verbs:
    if not file_set.scad_source:
        raise RuntimeError("Cannot build without OpenSCAD source file")
    if not file_set.scad_source.exists():
        raise RuntimeError(f"Source file {file_set.scad_source} does not exist")
    print("\nBuilding...")
    process_result = subprocess.run([
        DEPS.OPENSCAD,
        '--hardwarnings',
        '--export-format', 'binstl',
        # Can't use --quiet here since it suppresses warnings
        '-o', file_set.model,
        file_set.scad_source
    ], stdout=debug_output, stderr=filter_and_indent_stdout)

    if process_result.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {process_result.returncode}")

if 'orient' in verbs:
    print("\nAuto-orienting...")

    file_set.oriented_model = file_set.build_dir / f"{file_set.model.stem}-oriented.stl"

    # This was basically copied from Tweaker.py since it doesn't have a code-based interface
    # to handle all meshes at once
    file_handler = FileHandler.FileHandler()
    mesh_objects = file_handler.load_mesh(file_set.model)
    info = {}  # This is what Tweaker calls this; it needs a better name
    for part, content in mesh_objects.items():
        tweak_res = MeshTweaker.Tweak(
            content['mesh'],
            extended_mode=True,
            verbose=False,
            show_progress=False,
        )
        info[part] = dict(matrix=tweak_res.matrix, tweaker_stats=tweak_res)

        file_handler.write_mesh(mesh_objects, info, file_set.oriented_model, 'binarystl')

mesh_metrics = None
if 'info' in verbs:
    mesh = stl.mesh.Mesh.from_file(file_set.model_to_project())
    
    mesh_metrics = MeshMetrics(
        xrange=(mesh.x.min(), mesh.x.max()),
        yrange=(mesh.y.min(), mesh.y.max()),
        zrange=(mesh.z.min(), mesh.z.max()),
    )

    sizes = mesh_metrics.sizes()
    mid = mesh_metrics.midpoints()
    print(f"\nMesh size: x={sizes.x:.2f}, y={sizes.y:.2f}, z={sizes.z:.2f}")
    print(f"Mesh center: x={mid.x:.2f}, y={mid.y:.2f}, z={mid.z:.2f}")

if 'sketch' in verbs:
    print("\nSketching...")
    scad_code = PROJECTION_CODE[options.sketch_view].replace("\n", '')

    file_set.projected_model = file_set.build_dir / f"{file_set.model_to_project().stem}-{options.sketch_view}.stl"

    sizes = mesh_metrics.sizes()
    midpoints = mesh_metrics.midpoints()

    process_result = subprocess.run([
        DEPS.OPENSCAD,
        '--quiet',
        '--hardwarnings',
        '--export-format', 'binstl',
        '-o', file_set.projected_model,
        # We use json.dumps below to escape the path in case it contains backslashes or other special chars
        '-D', f'stl_file={json.dumps(str(file_set.model_to_project().absolute()))};',
        '-D', f'x_mid={midpoints.x:.2f};',
        '-D', f'y_mid={midpoints.y:.2f};',
        '-D', f'z_mid={midpoints.z:.2f};',
        '-D', f'x_size={sizes.x:.2f};',
        '-D', f'y_size={sizes.y:.2f};',
        '-D', f'z_size={sizes.z:.2f};',
        '-D', scad_code,
        os.devnull,
    ], stdout=debug_output, stderr=filter_and_indent_stdout)

    if process_result.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {process_result.returncode}")

    # Insert a projection overlay to print projections quicker
    options.overlays.insert(0, 'sketch')


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

