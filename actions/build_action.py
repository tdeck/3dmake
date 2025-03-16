import os
import subprocess
import platform
import sys
from typing import TextIO
from pathlib import Path
from time import time, sleep, strftime
from datetime import timedelta

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

def format_build_time(seconds: float) -> str:
    td = timedelta(seconds=int(seconds))
    return str(td) # This does an OK job; could be better

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
            "\nRun 3dm install-libraries."
        )

    lib_include_dirs = [
            lib_registry.lookup(lib_name).latest_version_dir()
            for lib_name in ctx.options.libraries
    ]

    for local_lib in ctx.options.local_libraries:
        ll_path = Path(local_lib)
        if not ll_path.is_absolute():
            ll_path = ll_path.absolute()
            # TODO if these paths are relative, it'll work now because of how
            # 3dm is always run from a project root, but it may not work in the
            # future
        lib_include_dirs.append(ll_path)

    tty_output_mode = sys.stdout.isatty()
    
    if ctx.options.debug:
        filter_stdout = stdout
    else:
        filter_stdout = FilterPipe(
            stdout,
            filter_fn=should_print_openscad_log,
            pad_lines_to=20 if tty_output_mode else 0,
        )

    cmd_options = [
        '--export-format', 'binstl',
        # Can't use --quiet here since it suppresses warnings
        '-o', ctx.files.model,
    ]

    if ctx.options.strict_warnings:
        cmd_options.append('--hardwarnings')

    envvars = dict(os.environ, OPENSCADPATH=construct_OPENSCADPATH(lib_include_dirs))

    start_time = time()
    subproc = subprocess.Popen(
        [DEPS.OPENSCAD] + cmd_options + [ctx.files.scad_source],
        stdout=debug_stdout,
        stderr=filter_stdout,
        env=envvars,
    )

    last_printed_time = None
    while subproc.poll() is None:
        runtime = time() - start_time
        # We don't want to be chewing up CPU busy-waiting, but we also don't 
        # want to make short builds slower, so we try to strike a balance with
        # these sleeps
        if runtime < 1:
            sleep(.05)
        elif runtime < 10:
            sleep(.1)
        else:
            sleep(.5)
        # We use print here instead of stdout.write because we will overwrite
        # the indent
        if tty_output_mode:  # Print running build time indicator in TTY
            time_str = format_build_time(runtime)
            # Our printed timestamps have a 1 second granularity; if we write out lines
            # multiple times per second the screen reader may flood us with updates,
            # so we don't print every single time
            if time_str != last_printed_time:
                last_printed_time = time_str
                print("\r" + ' ' * 20, end='') # Clear the line
                print("\r" + stdout.indent_str + "Build time " + time_str, end='\r', flush=True)
                # Note: The \r at the end here means that if OpenSCAD writes a log
                # from the FilteredPipe thread, it'll appear at the start of the
                # line and (most likely) overwrite the build time

    if not tty_output_mode:  # Print single build time indicator in pipeline
        print(stdout.indent_str + "Build time " + format_build_time(runtime), end='')

    print() # Need a newline

    if subproc.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {subproc.returncode}")
