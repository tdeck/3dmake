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

def _default_install_base() -> Path:
    if platform.system() == 'Windows':
        # On Windows user_data_path and user_config_path
        # are both LOCALAPPDATA which is a problem
        return Path(os.environ['LOCALAPPDATA']) / 'Programs' / '3dmake'
    return user_data_path('3dmake', None)

INSTALL_DIR = (
    Path(os.environ['THREEDMAKE_INSTALL_DIR'])
    if 'THREEDMAKE_INSTALL_DIR' in os.environ
    else _default_install_base() / f'v{VERSION}'
)

@dataclass
class Dependencies:
    OPENSCAD: Path
    SLICER: Path

def get_deps() -> Dependencies:
    os_type = platform.system()
    bundled_deps = {
        'Linux': Dependencies(
            Path('deps/linux/OpenSCAD.AppImage'),
            Path('deps/linux/PrusaSlicer.AppImage'),
        ),
        'Windows': Dependencies(
            Path('deps/windows/openscad/openscad.exe'),
            Path('deps/windows/prusaslicer/prusa-slicer-console.exe'),
        ),
        'Darwin': Dependencies(
            Path('deps/macos/OpenSCAD.app/Contents/MacOS/OpenSCAD'),
            Path('deps/macos/PrusaSlicer.app/Contents/MacOS/PrusaSlicer'),
        ),
    }

    if os_type not in bundled_deps:
        raise RuntimeError(f"Unsupported operating system: {os_type}")

    if openscad_env := os.environ.get('THREEDMAKE_OPENSCAD_PATH'):
        openscad_path = Path(openscad_env)
    else:
        openscad_path = SCRIPT_DIR / bundled_deps[os_type].OPENSCAD

    if slicer_env := os.environ.get('THREEDMAKE_SLICER_PATH'):
        slicer_path = Path(slicer_env)
    else:
        slicer_path = SCRIPT_DIR / bundled_deps[os_type].SLICER

    return Dependencies(openscad_path, slicer_path)

DEPS = get_deps()
BAMBU_3MF_TEMPLATE_PATH = SCRIPT_DIR / 'template.gcode.3mf'
BUNDLED_SCAD_LIB_PATH = SCRIPT_DIR / "scad_library"
