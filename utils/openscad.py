import os
import platform
import re
import subprocess
from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from utils.bundle_paths import DEPS
from utils.output_streams import OutputStream, AccumulatorStream, OutputPipe

_QUOTED = r'"((?:[^"\\]|\\.)*)"'
_3DM_PATTERN = re.compile(rf'^ECHO: "___\[3DMAKE\]___", {_QUOTED}, {_QUOTED}$')


def _unescape(s: str) -> str:
    return re.sub(r'\\(.)', lambda m: m.group(1), s)


@dataclass
class OpenSCADRun:
    process: subprocess.Popen
    logged_key_values: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


def _collect_3dm_log(line: str, kv: dict[str, list[str]]) -> None:
    match = _3DM_PATTERN.match(line)
    if match:
        kv[_unescape(match.group(1))].append(_unescape(match.group(2)))


def _construct_openscadpath(dirs: list[Path]) -> str:
    sep = ';' if platform.system() == 'Windows' else ':'
    return sep.join(str(d) for d in dirs)


@contextmanager
def run_openscad(
    model_file: Path,
    output_file: Path,
    stdout: OutputStream,
    stderr: OutputStream,
    lib_include_dirs: list[Path],
    var_defs: dict[str, str] = {},
    hardwarnings: bool = False,
) -> Generator[OpenSCADRun, None, None]:
    cmd = [DEPS.OPENSCAD, '--export-format', 'binstl', '-o', output_file]
    if hardwarnings:
        cmd.append('--hardwarnings')
    for k, v in var_defs.items():
        cmd += ['-D', f'{k}="{v}";']
    cmd.append(model_file)
    env = dict(os.environ, OPENSCADPATH=_construct_openscadpath(lib_include_dirs))

    run = OpenSCADRun(process=None)
    stderr_stream = AccumulatorStream(
        sink=stderr,
        reader_fn=_collect_3dm_log,
        accumulator=run.logged_key_values,
    )

    with OutputPipe(stdout) as stdout_pipe, OutputPipe(stderr_stream) as stderr_pipe:
        run.process = subprocess.Popen(cmd, stdout=stdout_pipe, stderr=stderr_pipe, env=env)
        try:
            yield run
        finally:
            run.process.wait()


def should_print_openscad_log(line: str) -> bool:
    """
    Returns true if the log line matches an ERROR, WARNING, or TRACE pattern.

    OpenSCAD doesn't provide a good way to filter logs on the command line so we must resort to this.
    """

    if _3DM_PATTERN.match(line):
        return False

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
