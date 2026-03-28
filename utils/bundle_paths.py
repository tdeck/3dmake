import os
import sys
from pathlib import Path
from dataclasses import dataclass
import platform
from platformdirs import user_data_path
from version import VERSION

IS_PYINSTALLER_DISTRIBUTION = getattr(sys, 'frozen', False)

if IS_PYINSTALLER_DISTRIBUTION:
    # Special case for PyInstaller
    SCRIPT_DIR = Path(sys._MEIPASS)
    SCRIPT_BIN_PATH = Path(sys.executable).absolute()
else:
    SCRIPT_DIR = Path(sys.path[0])
    SCRIPT_BIN_PATH = Path(sys.argv[0]).absolute()

INSTALL_DIR = (
    Path(os.environ['THREEDMAKE_INSTALL_DIR'])
    if 'THREEDMAKE_INSTALL_DIR' in os.environ
    else user_data_path('3dmake', None) / f'v{VERSION}'
)

@dataclass
class Dependencies:
    OPENSCAD: Path
    SLICER: Path

def get_deps() -> Dependencies:
    os_type = platform.system()

    if openscad_env := os.environ.get('THREEDMAKE_OPENSCAD_PATH'):
        openscad_path = Path(openscad_env)
    else:
        openscad_path = SCRIPT_DIR.joinpath(
            {
                'Linux': 'deps/linux/OpenSCAD.AppImage',
                'Windows': 'deps/windows/openscad/openscad.exe',
            }[os_type]
        )

    if slicer_env := os.environ.get('THREEDMAKE_SLICER_PATH'):
        slicer_path = Path(slicer_env)
    else:
        slicer_path = SCRIPT_DIR.joinpath(
            {
                'Linux': 'deps/linux/PrusaSlicer.AppImage',
                'Windows': 'deps/windows/prusaslicer/prusa-slicer-console.exe',
            }[os_type]
        )

    return Dependencies(openscad_path, slicer_path)

DEPS = get_deps()
BAMBU_3MF_TEMPLATE_PATH = SCRIPT_DIR / 'template.gcode.3mf'
BUNDLED_SCAD_LIB_PATH = SCRIPT_DIR / "scad_library"
