import os
import subprocess
from typing import TextIO
from pathlib import Path
import platform

from .framework import Context, pipeline_action
from utils.bundle_paths import DEPS
from utils.stream_wrappers import FilterPipe
from utils.openscad import should_print_openscad_log
from utils.libs import load_installed_libs

def construct_OPENSCADPATH(dirs: list[Path]) -> str:
    if platform.system() == 'Windows':
        path_sep = ';'
    else:
        path_sep = ':'

    return path_sep.join((str(d) for d in dirs))

@pipeline_action
def build(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Build the OpenSCAD model and produce an STL file '''

    if not ctx.files.scad_source:
        raise RuntimeError("Cannot build without OpenSCAD source file")
    if not ctx.files.scad_source.exists():
        raise RuntimeError(f"Source file {ctx.files.scad_source} does not exist")

    lib_registry = load_installed_libs(ctx.config_dir)
    needed_libs = set(ctx.options.libraries) - set(lib_registry.libs.keys())

    if needed_libs:
        raise RuntimeError(
            f"Some needed libraries are not installed: {' '.join(needed_libs) }"
            "\nRun 3dm install-libs."
        )

    lib_include_dirs = [
            lib_registry.lookup(lib_name).latest_version_dir()
            for lib_name in ctx.options.libraries
    ]
    
    if ctx.options.debug:
        filter_stdout = stdout
    else:
        filter_stdout = FilterPipe(
            stdout,
            filter_fn=should_print_openscad_log,
        )

    cmd_options = [
        '--export-format', 'binstl',
        # Can't use --quiet here since it suppresses warnings
        '-o', ctx.files.model,
    ]

    if ctx.options.strict_warnings:
        cmd_options.append('--hardwarnings')

    envvars = dict(os.environ, OPENSCADPATH=construct_OPENSCADPATH(lib_include_dirs))
    process_result = subprocess.run(
        [DEPS.OPENSCAD] + cmd_options + [ctx.files.scad_source],
        stdout=debug_stdout,
        stderr=filter_stdout,
        env=envvars,
    )

    if process_result.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {process_result.returncode}")
