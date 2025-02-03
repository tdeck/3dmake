import subprocess
from typing import TextIO

from .framework import Context, pipeline_action
from utils.bundle_paths import DEPS
from utils.stream_wrappers import FilterPipe
from utils.openscad import should_print_openscad_log

@pipeline_action
def build(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    if not ctx.files.scad_source:
        raise RuntimeError("Cannot build without OpenSCAD source file")
    if not ctx.files.scad_source.exists():
        raise RuntimeError(f"Source file {ctx.files.scad_source} does not exist")

    
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

    process_result = subprocess.run(
        [DEPS.OPENSCAD] + cmd_options + [ctx.files.scad_source],
        stdout=debug_stdout,
        stderr=filter_stdout,
    )

    if process_result.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {process_result.returncode}")
