import subprocess
import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass
import tempfile

import trimesh
import numpy as np
from .framework import Context, internal_action, pipeline_action
from .build_action import build
from .mesh_actions import measure_mesh
from utils.bundle_paths import DEPS
from utils.output_streams import OutputStream, FilterStream, OutputPipe
from utils.openscad import should_print_openscad_log, run_openscad
from utils.logging import throw_subprogram_error, show_subprocess_timer
from utils.libs import resolve_lib_include_dirs

SELECTED_PLANE_KEY = 'selected_preview_plane'

@internal_action
def ensure_previewable_model(
    ctx: Context, stdout: OutputStream, debug_stdout: OutputStream
):
    # This ensures we rebuild the model if we're doing a preview plane build, because
    # the plane is extracted based on the current SCAD code, and if the build is stale
    # it won't correspond properly.
    if ctx.options.view in NAMED_PROJECTION_CODE:
        return # No need for a fresh build
    elif ctx.build_metadata is not None:
        return # Already built, they ran `3dm build preview`

    # TODO this is a bit hacky because we're creating a new wrapper around stdout
    # rather than using the existing chain
    build(ctx)

@pipeline_action(
    gerund='preparing preview',
    input_file_type='.stl',
    implied_actions=[ensure_previewable_model, measure_mesh],
)
def preview(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Produce a 2-D representation of the object '''
    view_name = ctx.options.view
    scad_vars: dict[str, str] = {} # Values should be code literals

    if view_name in NAMED_PROJECTION_CODE: # One of the default silhouettes
        model_to_project = ctx.files.oriented_model or ctx.files.model
        to_svg_code = NAMED_PROJECTION_CODE[view_name]
        sizes = ctx.mesh_metrics.sizes()
        midpoints = ctx.mesh_metrics.midpoints()
        scad_vars = {
            'x_mid': f"{midpoints.x:.2f}",
            'y_mid': f"{midpoints.y:.2f}",
            'z_mid': f"{midpoints.z:.2f}",
            'x_size': f"{sizes.x:.2f}",
            'y_size': f"{sizes.y:.2f}",
            'z_size': f"{sizes.z:.2f}",
        }
    elif view_name in ctx.build_metadata.preview_plane_names: # Preview plane cross-section
        plane = build_and_locate_preview_plane(
            ctx,
            ctx.files.scad_source,
            view_name,
            debug_stdout,
        )
        # Must use the un-oriented model with preview planes so they align
        model_to_project = ctx.files.model
        to_svg_code = PREVIEW_PLANE_PROJECTION_CODE
        scad_vars = {
            "normal_vector": _format_scad_vector(plane.normal),
            "origin_vector": _format_scad_vector(plane.origin),
            "right_vector": _format_scad_vector(plane.right),
        }
    else:
        raise RuntimeError(f"No view or preview plane called '{view_name}' exists")

    stem = model_to_project.stem
    ctx.files.preview_svg = ctx.files.build_dir / f"{stem}-{view_name}.svg"
    ctx.files.projected_model = ctx.files.build_dir / f"{stem}-{view_name}.stl"

    filter_stderr = stdout if ctx.options.debug else FilterStream(stdout, should_print_openscad_log)

    debug_stdout.writeln('Projecting to SVG...')
    with OutputPipe(debug_stdout) as debug_pipe, OutputPipe(filter_stderr) as stderr_pipe:
        # Step 1: Project to SVG
        cmd = [
            DEPS.OPENSCAD,
            '--quiet',
            '--hardwarnings',
            '--export-format', 'svg',
            '-o', ctx.files.preview_svg,
            '-D', f'stl_file={json.dumps(str(model_to_project.absolute()))};',
        ]
        for k, v in scad_vars.items():
            cmd += ['-D', f"{k}={v};"]
        cmd += [
            '-D', to_svg_code.replace("\n", ''),
            os.devnull, # No source file
        ]
        debug_stdout.writeln(f"SVG projection cmd: {cmd}")
        result = subprocess.run(cmd, stdout=debug_pipe, stderr=stderr_pipe)

        if result.returncode != 0:
            throw_subprogram_error('OpenSCAD', result.returncode, ctx.options.debug)

        debug_stdout.writeln('Extruding to STL...')
        # Step 2: Extrude the SVG to STL
        extrude_code = f'HEIGHT = .6; linear_extrude(HEIGHT) import({json.dumps(str(ctx.files.preview_svg.absolute()))});'
        result = subprocess.run([
            DEPS.OPENSCAD,
            '--quiet',
            '--hardwarnings',
            '--export-format', 'binstl',
            '-o', ctx.files.projected_model,
            '-D', extrude_code,
            os.devnull, # No source file
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


def _format_scad_vector(vec: list[float] | tuple[float]) -> str:
    return '[' + ','.join([f"{k:.4f}" for k in vec]) + ']'

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
    "Could not find a valid preview plane. Was the plane part of a subtraction or intersection?"
)

@dataclass(kw_only=True)
class Plane:
    origin: tuple[float, float, float]
    normal: tuple[float, float, float]
    right: tuple[float, float, float]

def build_and_locate_preview_plane(
    ctx: Context,
    model_source: Path,
    plane_name: str,
    debug_stdout: OutputStream
) -> Plane:
    with tempfile.TemporaryDirectory() as stl_dir:
        plane_stl = Path(stl_dir) / "plane.stl"
        with run_openscad(
            model_file=model_source,
            output_file=plane_stl,
            stdout=debug_stdout,
            stderr=debug_stdout,
            lib_include_dirs=resolve_lib_include_dirs(
                ctx.config_dir,
                ctx.options,
            ),
            hardwarnings=False,
            var_defs={"$THREEDMAKE_PREVIEW_PLANE": plane_name},
        ) as run:
            show_subprocess_timer(run.process, 'Resolving preview plane', debug_stdout)

        selected_planes = run.logged_key_values.get(SELECTED_PLANE_KEY, [])
        debug_stdout.writeln(f"Selected planes: {selected_planes}")
        if selected_planes.count(plane_name) > 1:
            raise RuntimeError(
                f"More than one plane with name '{plane_name}' was generated."
                " Ensure that the plane function is only being called once."
            )
        elif selected_planes != [plane_name]:
            raise RuntimeError("Unable to select preview plane. This may be a bug worth reporting.")

        return extract_stl_preview_plane(plane_stl, debug_stdout)


def extract_stl_preview_plane(stl_file: Path, debug_stdout: OutputStream) -> Plane:
    CUTOFF_COORD = 100_000
    PLANE_TOLERANCE = 1 # TODO adjust

    with open(stl_file, 'rb') as fh:
        tm = trimesh.Trimesh(**trimesh.exchange.stl.load_stl_binary(fh))

    # Find all the vertices that could be part of a preview plane.
    # Expect 5: the 4 large base corners plus 1 orientation marker.
    all_far_indices = np.where(np.any(np.abs(tm.vertices) >= CUTOFF_COORD, axis=1))[0]

    if len(all_far_indices) != 5:
        raise INVALID_PLANE_ERROR

    # The 4 corners all sit at the same distance from the origin (SIZE*sqrt(2)).
    # The marker is at a different distance (SIZE+1000), so it's the outlier.
    all_far_vertices = tm.vertices[all_far_indices]
    distances = np.linalg.norm(all_far_vertices, axis=1)
    marker_local_idx = int(np.argmax(np.abs(distances - np.median(distances))))
    marker_vertex = all_far_vertices[marker_local_idx]
    corner_indices = np.delete(all_far_indices, marker_local_idx)
    corner_vertices = tm.vertices[corner_indices]

    # Check that the 4 base corners are coplanar
    plane_origin, plane_normal = trimesh.points.plane_fit(corner_vertices)
    plane_distances = trimesh.points.point_plane_distance(corner_vertices, plane_normal, plane_origin)
    # Note: I have confirmed that point_plane_distance returns a signed value
    if np.any(np.abs(plane_distances) > PLANE_TOLERANCE):
        debug_stdout.writeln(f"Plane distances exceed tolerance: {plane_distances}")
        raise INVALID_PLANE_ERROR

    # Derive the in-plane right direction from the marker.
    # The 4 corners are symmetric so their centroid is at the plane origin.
    marker_dir = marker_vertex - corner_vertices.mean(axis=0)
    marker_dir -= np.dot(marker_dir, plane_normal) * plane_normal  # project onto plane
    plane_right = marker_dir / np.linalg.norm(marker_dir)

    # Now identify the direction of the pyramid apex, so we can tell if the plane
    # should be inverted. It's very likely that the plane will have been merged with
    # some other solid, so we instead figure out which direction the extreme corner's
    # non-planar vectors are pointing.
    min_dist = 0.0
    max_dist = 0.0
    for plane_vertex_idx in corner_indices:
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
        debug_stdout.writeln(f"No peak found; min_dist={min_dist} max_dist={max_dist}")
        raise INVALID_PLANE_ERROR
    elif min_dist < -PLANE_TOLERANCE and max_dist > PLANE_TOLERANCE:
        # Peaks on either side?
        debug_stdout.writeln(f">1 peak; min_dist={min_dist} max_dist={max_dist}")
        raise INVALID_PLANE_ERROR
    elif abs(min_dist) > max_dist:
        # This means the peak is below the plane, so we invert the normal
        debug_stdout.writeln("Inverting plane normal")
        plane_normal = -plane_normal

    debug_stdout.writeln(
        f"Detected preview origin={plane_origin} normal={plane_normal} right={plane_right}"
    )

    return Plane(origin=plane_origin, normal=plane_normal, right=tuple(plane_right))
    

NAMED_PROJECTION_CODE = {
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

# Do not use // line comments in this code as line breaks will be removed
PREVIEW_PLANE_PROJECTION_CODE = '''
    module plane_aligned_model() {
        n_hat = normal_vector / norm(normal_vector);
        plane_right = right_vector / norm(right_vector);
        plane_up = cross(n_hat, plane_right); /* the +z dir (vertical planes) or +y dir (horizontal) */

        /* Build a rotation matrix with rows [plane_right, plane_up, n_hat].
           This maps: plane_right -> X, plane_up -> Y, n_hat -> Z.
           After this, projection(cut=true) cuts at z=0, which is the plane. */
        multmatrix([
            [plane_right[0], plane_right[1], plane_right[2], 0],
            [plane_up[0],    plane_up[1],    plane_up[2],    0],
            [n_hat[0],       n_hat[1],       n_hat[2],       0],
            [0,              0,              0,              1]
        ]) translate(-origin_vector) import(stl_file);
    }

    projection(cut=true) plane_aligned_model();
'''
