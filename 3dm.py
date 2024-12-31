#! /usr/bin/env python3

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Literal, Union
import argparse
import os
import sys
import subprocess
import tempfile
import threading
import tomllib
import platform

import requests
import stl.mesh
from tweaker3 import MeshTweaker, FileHandler

if getattr(sys, 'frozen', False):
    # Special case for PyInstaller
    SCRIPT_DIR = Path(sys._MEIPASS)
else:
    SCRIPT_DIR = Path(sys.path[0])

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


SUPPORTED_VERBS = {
    'info',
    'build',
    'orient',
    'project',
    'slice',
    'print',
}

PROJECTION_CODE = {
    # These all receive the following vars:
    # stl_file, x_mid, y_mid, z_mid, x_size, y_size, z_size
    '3view': '''
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
    'project': 'info',  # The project step needs model dimensions to arrange the model
}


DEPS = get_deps()
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / ".config") / "3dmake"
PROFILES_DIR = CONFIG_DIR / 'profiles'
OVERLAYS_DIR = CONFIG_DIR / 'overlays'

class IndentStream:
    def __init__(self, wrapped_stream, indent=4):
        self.wrapped_stream = wrapped_stream
        self.indent_str = ' ' * indent
        self.pipe_read, self.pipe_write = os.pipe()

        # Start a thread to read from the pipe and forward indented output
        self._start_reader_thread()

    def _start_reader_thread(self):
        def _reader():
            with os.fdopen(self.pipe_read, 'r') as pipe:
                for line in pipe:
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
    projection: str
    printer_profile: str
    default_model: str
    scale: Union[float, Literal["auto"]] = 1.0
    overlays: List[str] = field(default_factory=list)
    octoprint_host: Optional[str] = None
    octoprint_key: Optional[str] = None
    auto_start_prints: bool = False

@dataclass
class FileSet:
    name: str = 'default'
    build_dir: Path = Path('build') # TODO based on options
    # TODO scad_file: Optional[Path] = None
    scad_source: Optional[Path] = Path("src/main.scad") # TODO based on options
    model: Optional[Path] = Path('build/model.stl') # TODO based on options
    oriented_model: Optional[Path] = None
    projected_model: Optional[Path] = None
    sliced_gcode: Optional[Path] = None

    def model_to_project(self) -> Optional[Path]:
        return self.oriented_model or self.model

    def model_to_slice(self) -> Optional[Path]:
        return self.projected_model or self.oriented_model or self.model

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


parser = argparse.ArgumentParser(
    prog='3dmake',
)

parser.add_argument('-s', '--scale') # can be either "auto" or a float
parser.add_argument('-p', '--profile', type=str)
parser.add_argument('-o', '--overlay', action='extend', nargs='*')
parser.add_argument('extra', nargs='+')

args = parser.parse_args()

extras = args.extra
infiles = []
while extras and '.' in extras[-1]:
    infiles.append(extras.pop())

verbs = set([x.lower() for x in extras])

file_set = FileSet()
options, project_root = load_config()

if args.scale:
    if args.scale.replace('.', '').isdecimal():
        options.scale = float(args.scale)
    elif args.scale.lower() == 'auto':
        options.scale = 'auto'
    else:
        raise RuntimeError("Invalid value for --scale, must be a decimal number or auto")

if args.profile:
    options.printer_profile = args.profile

if options.scale == 'auto':
    raise NotImplementedError("Auto-scaling is not supported yet") # TODO 

if len(infiles) > 1:
    raise RuntimeError("Multiple inputs not supported yet")
elif infiles:
    single_infile = Path(infiles[0])
    extension = single_infile.suffix.lower()

    file_set.build_dir = Path(tempfile.mkdtemp())
    print("Build dir:", file_set.build_dir) # TODO
    file_set.name = single_infile.stem  # Derive the model name from the STL name

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
    file_set.name = options.project_name
    file_set.scad_source = project_root / "src" / f"{options.default_model}.scad"
else:
    raise RuntimeError("Must either specify input file or run in a 3dmake project directory")

if not len(verbs):
    raise RuntimeError("Must provide a verb")

# Check verbs and insert any implied ones
for verb in list(verbs):
    if verb not in SUPPORTED_VERBS:
        raise RuntimeError(f"Unknown verb '{verb}'")
    if verb in IMPLIED_VERBS:
        verbs.add(IMPLIED_VERBS[verb])

if args.overlay:
    options.overlays = args.overlay

indent_stdout = IndentStream(sys.stdout)

if 'build' in verbs:
    if not file_set.scad_source:
        raise RuntimeError("Cannot build without OpenSCAD source file")
    if not file_set.scad_source.exists():
        raise RuntimeError(f"Source file {file_set.scad_source} does not exist")
    print("\nBuilding...")
    subprocess.run([
        DEPS.OPENSCAD,
        '--hardwarnings',
        '--export-format', 'binstl',
        '--quiet',
        '-o', file_set.model,
        file_set.scad_source
    ], stdout=indent_stdout, stderr=indent_stdout)

if 'orient' in verbs:
    print("\nAuto-orienting...")

    file_set.oriented_model = file_set.build_dir / 'oriented.stl' 

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

if 'project' in verbs:
    print("\nProjecting...")
    scad_code = PROJECTION_CODE[options.projection].replace("\n", '')

    file_set.projected_model = file_set.build_dir / 'projected.stl' 

    sizes = mesh_metrics.sizes()
    midpoints = mesh_metrics.midpoints()

    subprocess.run([
        DEPS.OPENSCAD,
        '--quiet',
        '--hardwarnings',
        '--export-format', 'binstl',
        '-o', file_set.projected_model,
        '-D', f'stl_file="{file_set.model_to_project().absolute()}";',
        '-D', f'x_mid={midpoints.x:.2f};',
        '-D', f'y_mid={midpoints.y:.2f};',
        '-D', f'z_mid={midpoints.z:.2f};',
        '-D', f'x_size={sizes.x:.2f};',
        '-D', f'y_size={sizes.y:.2f};',
        '-D', f'z_size={sizes.z:.2f};',
        '-D', scad_code,
        os.devnull,
    ], stdout=indent_stdout, stderr=indent_stdout)

    # Insert a projection overlay to print projections quicker
    options.overlays.insert(0, 'projection')

    print(file_set.projected_model) # TODO debug

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

    gcode_file = file_set.build_dir / 'sliced.gcode'
    
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
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=indent_stdout)

    file_set.sliced_gcode = gcode_file

if 'print' in verbs:
    print("\nPrinting...")
    server_filename = f"{file_set.name}.gcode"
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


# Input types
#   src+ (scad)
#   model+ (stl)
#   arrangement (stl)
#   projection (stl)
#   
