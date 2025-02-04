import subprocess
import os
import json
from typing import TextIO

from .framework import Context, pipeline_action
from .measure_action import measure_model
from utils.bundle_paths import DEPS
from utils.stream_wrappers import FilterPipe
from utils.openscad import should_print_openscad_log

@pipeline_action(
    gerund='preparing preview',
    implied_actions=[measure_model]
)
def preview(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Produce a 2-D representation of the object '''
    view_name = ctx.options.view
    if view_name not in PROJECTION_CODE:
        raise RuntimeError(f"The preview view '{view_name}' does not exist")

    scad_code = PROJECTION_CODE[view_name].replace("\n", '')

    ctx.files.projected_model = ctx.files.build_dir / f"{ctx.files.model_to_project().stem}-{view_name}.stl"

    sizes = ctx.mesh_metrics.sizes()
    midpoints = ctx.mesh_metrics.midpoints()

    if ctx.options.debug:
        filter_stdout = stdout
    else:
        filter_stdout = FilterPipe(
            stdout,
            filter_fn=should_print_openscad_log,
        )

    process_result = subprocess.run([
        DEPS.OPENSCAD,
        '--quiet',
        '--hardwarnings',
        '--export-format', 'binstl',
        '-o', ctx.files.projected_model,
        # We use json.dumps below to escape the path in case it contains backslashes or other special chars
        '-D', f'stl_file={json.dumps(str(ctx.files.model_to_project().absolute()))};',
        '-D', f'x_mid={midpoints.x:.2f};',
        '-D', f'y_mid={midpoints.y:.2f};',
        '-D', f'z_mid={midpoints.z:.2f};',
        '-D', f'x_size={sizes.x:.2f};',
        '-D', f'y_size={sizes.y:.2f};',
        '-D', f'z_size={sizes.z:.2f};',
        '-D', scad_code,
        os.devnull,
    ], stdout=debug_stdout, stderr=filter_stdout)

    if process_result.returncode != 0:
        raise RuntimeError(f"    Command failed with return code {process_result.returncode}")

    # Insert a projection overlay to print projections quicker
    ctx.options.overlays.insert(0, 'preview')

PROJECTION_CODE = {
    # These all receive the following vars:
    # stl_file, x_mid, y_mid, z_mid, x_size, y_size, z_size
    # Do not use // line comments in this code as line breaks will be removed
    '3sil': '''
        HEIGHT = .6;
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        linear_extrude(HEIGHT) {
            /* Top */
            translate([0, y_size/2 + z_size/2 + SPACING/*z_size + SPACING */, 0]) projection() model();

            /* Left */
            translate([-x_size/2 - y_size/2 - SPACING, 0, 0]) projection() rotate([-90, 90, 0]) model();

            /* Front */
            projection() rotate([-90, 0, 0]) model();
        }
    ''',
    'topsil': '''
        HEIGHT = .6;
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        linear_extrude(HEIGHT) {
            /* Top */
            projection() model();
        }
    ''',
    'leftsil': '''
        HEIGHT = .6;
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        linear_extrude(HEIGHT) {
            /* Left */
            projection() rotate([-90, 90, 0]) model();
        }
    ''',
    'rightsil': '''
        HEIGHT = .6;
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        linear_extrude(HEIGHT) {
            /* Right */
            projection() rotate([-90, -90, 0]) model();
        }
    ''',
    'frontsil': '''
        HEIGHT = .6;
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        linear_extrude(HEIGHT) {
            /* Front */
            projection() rotate([-90, 0, 0]) model();
        }
    ''',
    'backsil': '''
        HEIGHT = .6;
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        linear_extrude(HEIGHT) {
            /* Back */
            projection() rotate([-90, 180, 0]) model();
        }
    '''
}
