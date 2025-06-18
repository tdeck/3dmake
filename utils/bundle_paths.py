import sys
from pathlib import Path
from dataclasses import dataclass
import platform

if getattr(sys, 'frozen', False):
    # Special case for PyInstaller
    SCRIPT_DIR = Path(sys._MEIPASS)
    SCRIPT_BIN_PATH = Path(sys.executable).absolute()
else:
    SCRIPT_DIR = Path(sys.path[0])
    SCRIPT_BIN_PATH = Path(sys.argv[0]).absolute()

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

DEPS = get_deps()
BAMBU_3MF_TEMPLATE_PATH = SCRIPT_DIR / 'template.gcode.3mf'
