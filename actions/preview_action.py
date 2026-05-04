import subprocess
import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass
import tempfile

import trimesh
import numpy as np
from .framework import Context, pipeline_action
from .mesh_actions import measure_mesh
from utils.bundle_paths import DEPS, BUNDLED_SCAD_LIB_PATH
from utils.output_streams import OutputStream, FilterStream, OutputPipe
from utils.openscad import should_print_openscad_log, run_openscad
from utils.logging import throw_subprogram_error

@pipeline_action(
    gerund='preparing preview',
    input_file_type='.stl',
    implied_actions=[measure_mesh]
)
def preview(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Produce a 2-D representation of the object '''
    view_name = ctx.options.view
    if view_name in PROJECTION_CODE:
        pass
    elif view_name in ctx.build_metadata.preview_plane_names:
        build_and_locate_preview_plane(
            ctx.files.scad_source,
            view_name,
            debug_stdout,
        )
        # TODO what if not built?
        # TODO must use un-oriented model for preview projection
    if view_name not in PROJECTION_CODE:
        raise RuntimeError(f"The preview view '{view_name}' does not exist")

    svg_code = PROJECTION_CODE[view_name].replace("\n", '')

    stem = ctx.files.model_to_project().stem
    ctx.files.preview_svg = ctx.files.build_dir / f"{stem}-{view_name}.svg"
    ctx.files.projected_model = ctx.files.build_dir / f"{stem}-{view_name}.stl"

    sizes = ctx.mesh_metrics.sizes()
    midpoints = ctx.mesh_metrics.midpoints()

    filter_stderr = stdout if ctx.options.debug else FilterStream(stdout, should_print_openscad_log)

    with OutputPipe(debug_stdout) as debug_pipe, OutputPipe(filter_stderr) as stderr_pipe:
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
        ], stdout=debug_pipe, stderr=stderr_pipe)

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
        ], stdout=debug_pipe, stderr=stderr_pipe)

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


INVALID_PLANE_ERROR = RuntimeError(
    # TODO
    "Could not find a valid preview plane. Was the plane part of a subtraction or intersection?"
)

@dataclass(kw_only=True)
class Plane:
    origin: tuple[float, float, float]
    normal: tuple[float, float, float]

def build_and_locate_preview_plane(model_source: Path, plane_name: str, debug_stdout: OutputStream):
    with tempfile.TemporaryDirectory() as stl_dir:
        #plane_stl = Path(stl_dir) / "plane.stl"
        plane_stl = Path("/tmp/troysplane.stl") # TODO DO NOT MERGE
        lib_include_dirs = [BUNDLED_SCAD_LIB_PATH] # TODO DO NOT MERGE
        with run_openscad(
            model_file=model_source,
            output_file=plane_stl,
            stdout=debug_stdout, # TODO collect info
            stderr=debug_stdout,
            lib_include_dirs=lib_include_dirs,
            hardwarnings=False,
            var_defs={"$THREEDMAKE_PREVIEW_PLANE": plane_name},
        ) as run:
            pass # TODO add a timer here

        print("Preview plane", extract_stl_preview_plane(plane_stl))


def extract_stl_preview_plane(stl_file: Path) -> Plane:
    CUTOFF_COORD = 100_000
    PLANE_TOLERANCE = 1 # TODO adjust

    with open(stl_file, 'rb') as fh:
        tm = trimesh.Trimesh(**trimesh.exchange.stl.load_stl_binary(fh))

    # Find all the vertices that could be part of a preview plane
    far_vertex_indices = np.where(np.any(np.abs(tm.vertices) >= CUTOFF_COORD, axis=1))[0]

    if len(far_vertex_indices) != 4:
        raise INVALID_PLANE_ERROR

    # Since the plane object is a giant pyramid with a low peak, each of these
    # vertices should be one corner of the base. 

    # Check that the base points are coplanar
    far_vertices = tm.vertices[far_vertex_indices]
    plane_origin, plane_normal = trimesh.points.plane_fit(far_vertices)
    plane_distances = trimesh.points.point_plane_distance(far_vertices, plane_normal, plane_origin)
    # Note: I have confirmed that point_plane_distance returns a signed value
    if np.any(np.abs(plane_distances) > PLANE_TOLERANCE):
        raise INVALID_PLANE_ERROR

    # Now identify the direction of the pyramid apex, so we can tell if the plane
    # should be inverted. It's very likely that the plane will have been merged with
    # some other solid, so we instead figure out which direction the extreme corner's
    # non-planar vectors are pointing.
    min_dist = 0.0
    max_dist = 0.0
    for plane_vertex_idx in far_vertex_indices:
        neighbor_vertices = tm.vertices[tm.vertex_neighbors[plane_vertex_idx]]
        neighbor_plane_dists = trimesh.points.point_plane_distance(
            neighbor_vertices,
            plane_normal,
            plane_origin
        )
        min_dist = min(neighbor_plane_dists.min(), min_dist)
        max_dist = max(neighbor_plane_dists.max(), max_dist)

    if min_dist > -PLANE_TOLERANCE and max_dist < PLANE_TOLERANCE:
        # No peak found
        raise INVALID_PLANE_ERROR
    elif min_dist < -PLANE_TOLERANCE and max_dist > PLANE_TOLERANCE:
        # Peaks on either side?
        raise INVALID_PLANE_ERROR
    elif abs(min_dist) > max_dist:
        # This means the peak is below the plane, so we invert the normal
        plane_normal = -plane_normal

    return Plane(origin=plane_origin, normal=plane_normal)
    

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
