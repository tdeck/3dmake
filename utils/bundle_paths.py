import sys
from pathlib import Path
from dataclasses import dataclass
import platform

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

DEPS = get_deps()
