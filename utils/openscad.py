import os
import platform
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import TextIO

from utils.bundle_paths import DEPS

_QUOTED = r'"((?:[^"\\]|\\.)*)"'
_3DM_PATTERN = re.compile(rf'^ECHO: "___\[3DMAKE\]___", {_QUOTED}, {_QUOTED}$')


def _unescape(s: str) -> str:
    return re.sub(r'\\(.)', lambda m: m.group(1), s)


class OpenSCADMessageCollector:
    def __init__(self):
        self.logged_key_values: dict[str, list[str]] = defaultdict(list)

    def should_print(self, line: str) -> bool:
        match = _3DM_PATTERN.match(line)
        if match:
            self.logged_key_values[_unescape(match.group(1))].append(_unescape(match.group(2)))
            return False
        return should_print_openscad_log(line)


def _construct_openscadpath(dirs: list[Path]) -> str:
    sep = ';' if platform.system() == 'Windows' else ':'
    return sep.join(str(d) for d in dirs)


def run_openscad(
    model_file: Path,
    output_file: Path,
    stdout: TextIO,
    stderr: TextIO,
    lib_include_dirs: list[Path],
    var_defs: dict[str, str] = {},
    hardwarnings: bool = False,
) -> subprocess.Popen:
    cmd = [DEPS.OPENSCAD, '--export-format', 'binstl', '-o', output_file]
    if hardwarnings:
        cmd.append('--hardwarnings')
    for k, v in var_defs.items():
        cmd += ['-D', f'{k}="{v}";']
    cmd.append(model_file)
    env = dict(os.environ, OPENSCADPATH=_construct_openscadpath(lib_include_dirs))
    return subprocess.Popen(cmd, stdout=stdout, stderr=stderr, env=env)


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
