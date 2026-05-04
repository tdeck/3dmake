import sys

from .framework import Context, BuildMetadata, pipeline_action
from utils.output_streams import OutputStream, FilterStream, TransformerStream
from utils.openscad import run_openscad, should_print_openscad_log
from utils.libs import resolve_lib_include_dirs
from utils.logging import throw_subprogram_error, show_subprocess_timer

@pipeline_action(input_file_type='.scad')
def build(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Build the OpenSCAD model and produce an STL file '''

    if not ctx.files.scad_source:
        raise RuntimeError("Cannot build without OpenSCAD source file")
    if not ctx.files.scad_source.exists():
        raise RuntimeError(f"Source file {ctx.files.scad_source} does not exist")

    lib_include_dirs = resolve_lib_include_dirs(ctx.config_dir, ctx.options)

    tty_output_mode = sys.stdout.isatty()

    if ctx.options.debug:
        scad_ostream = stdout
    else:
        scad_ostream = FilterStream(stdout, should_print_openscad_log)

    if tty_output_mode:
        # We need to pad the output lines so that they will fully overwrite our
        # constantly updating prompt when printed
        scad_ostream = TransformerStream(scad_ostream, lambda l: f"{l:<20}")

    with run_openscad(
        model_file=ctx.files.scad_source,
        output_file=ctx.files.model,
        stdout=debug_stdout,
        stderr=scad_ostream,
        lib_include_dirs=lib_include_dirs,
        hardwarnings=ctx.options.strict_warnings,
    ) as run:
        show_subprocess_timer(run.process, 'Build time', stdout)

    if run.process.returncode != 0:
        throw_subprogram_error('OpenSCAD', run.process.returncode, ctx.options.debug)

    ctx.build_metadata = BuildMetadata(
        preview_plane_names=set(run.logged_key_values.get("preview_plane_option", []))
    )
