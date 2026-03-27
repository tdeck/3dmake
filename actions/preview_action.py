import subprocess
import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TextIO

from .framework import Context, pipeline_action
from .mesh_actions import measure_mesh
from utils.bundle_paths import DEPS
from utils.stream_wrappers import FilterPipe
from utils.openscad import should_print_openscad_log
from utils.logging import throw_subprogram_error

@pipeline_action(
    gerund='preparing preview',
    input_file_type='.stl',
    implied_actions=[measure_mesh]
)
def preview(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Produce a 2-D representation of the object '''
    view_name = ctx.options.view
    if view_name not in PROJECTION_CODE:
        raise RuntimeError(f"The preview view '{view_name}' does not exist")

    svg_code = PROJECTION_CODE[view_name].replace("\n", '')

    stem = ctx.files.model_to_project().stem
    ctx.files.preview_svg = ctx.files.build_dir / f"{stem}-{view_name}.svg"
    ctx.files.projected_model = ctx.files.build_dir / f"{stem}-{view_name}.stl"

    sizes = ctx.mesh_metrics.sizes()
    midpoints = ctx.mesh_metrics.midpoints()

    if ctx.options.debug:
        filter_stdout = stdout
    else:
        filter_stdout = FilterPipe(
            stdout,
            filter_fn=should_print_openscad_log,
        )

    # Step 1: Project to SVG
    result = subprocess.run([
        DEPS.OPENSCAD,
        '--quiet',
        '--hardwarnings',
        '--export-format', 'svg',
        '-o', ctx.files.preview_svg,
        '-D', f'stl_file={json.dumps(str(ctx.files.model_to_project().absolute()))};',
        '-D', f'x_mid={midpoints.x:.2f};',
        '-D', f'y_mid={midpoints.y:.2f};',
        '-D', f'z_mid={midpoints.z:.2f};',
        '-D', f'x_size={sizes.x:.2f};',
        '-D', f'y_size={sizes.y:.2f};',
        '-D', f'z_size={sizes.z:.2f};',
        '-D', svg_code,
        os.devnull,
    ], stdout=debug_stdout, stderr=filter_stdout)

    if result.returncode != 0:
        throw_subprogram_error('OpenSCAD', result.returncode, ctx.options.debug)

    # Step 2: Extrude the SVG to STL
    extrude_code = f'HEIGHT = .6; linear_extrude(HEIGHT) import({json.dumps(str(ctx.files.preview_svg.absolute()))});'
    result = subprocess.run([
        DEPS.OPENSCAD,
        '--quiet',
        '--hardwarnings',
        '--export-format', 'binstl',
        '-o', ctx.files.projected_model,
        '-D', extrude_code,
        os.devnull,
    ], stdout=debug_stdout, stderr=filter_stdout)

    if result.returncode != 0:
        throw_subprogram_error('OpenSCAD', result.returncode, ctx.options.debug)

    # Update the style of the SVG paths so they'll produce a better tactile graphic
    _update_svg_path_style(
        ctx.files.preview_svg,
        ctx.options.svg_fill_color,
        ctx.options.svg_stroke_width
    )

    # Insert a projection overlay to print projections quicker
    ctx.options.overlays.insert(0, 'preview')


def _update_svg_path_style(svg_path: Path, fill_color: str, stroke_width: float):
    SVG_NS = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', SVG_NS)
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')

    tree = ET.parse(svg_path)
    root = tree.getroot()

    ns_prefix = f'{{{SVG_NS}}}' if root.tag.startswith('{') else ''
    for elem in root.iter(f'{ns_prefix}path'):
        elem.set('fill', fill_color)
        elem.set('stroke-width', str(stroke_width))

    tree.write(svg_path, xml_declaration=True, encoding='UTF-8')

PROJECTION_CODE = {
    # These all receive the following vars:
    # stl_file, x_mid, y_mid, z_mid, x_size, y_size, z_size
    # Do not use // line comments in this code as line breaks will be removed
    '3sil': '''
        SPACING = 10;

        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Top */
        translate([0, y_size/2 + z_size/2 + SPACING, 0]) projection() model();

        /* Left */
        translate([-x_size/2 - y_size/2 - SPACING, 0, 0]) projection() rotate([-90, 90, 0]) model();

        /* Front */
        projection() rotate([-90, 0, 0]) model();
    ''',
    'topsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Top */
        projection() model();
    ''',
    'leftsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Left */
        projection() rotate([-90, 90, 0]) model();
    ''',
    'rightsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Right */
        projection() rotate([-90, -90, 0]) model();
    ''',
    'frontsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Front */
        projection() rotate([-90, 0, 0]) model();
    ''',
    'backsil': '''
        module model() {
            translate([-x_mid, -y_mid, -z_mid]) import(stl_file);
        }

        /* Back */
        projection() rotate([-90, 180, 0]) model();
    '''
}
