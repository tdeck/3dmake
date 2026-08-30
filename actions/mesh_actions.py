import numpy as np
import stl.mesh

from .framework import Context, internal_action
from .scale_action import scale
from coretypes import MeshMetrics # TODO need a better home for this


def calculate_xy_widths(mesh: stl.mesh.Mesh) -> tuple[float, float]:
    """Calculate maximum width in XY plane (assuming rotation around Z only) and perpendicular width."""
    points = mesh.vectors[:, :, :2].reshape(-1, 2)
    points = np.unique(points, axis=0)
    if len(points) <= 1:
        return 0.0, 0.0

    try:
        from scipy.spatial import ConvexHull
        if len(points) >= 3:
            hull = ConvexHull(points)
            hull_points = points[hull.vertices]
        else:
            hull_points = points
    except Exception:
        hull_points = points

    diff = hull_points[:, None, :] - hull_points[None, :, :]
    dists_sq = np.sum(diff**2, axis=-1)
    i, j = np.unravel_index(np.argmax(dists_sq), dists_sq.shape)
    p1, p2 = hull_points[i], hull_points[j]
    max_width = float(np.sqrt(dists_sq[i, j]))

    if max_width > 0:
        vec = p2 - p1
        u = vec / np.linalg.norm(vec)
        u_perp = np.array([-u[1], u[0]])
        proj = np.dot(hull_points, u_perp)
        perp_width = float(np.max(proj) - np.min(proj))
    else:
        perp_width = 0.0

    return max_width, perp_width


@internal_action(implied_actions=[scale])
def load_mesh(ctx: Context, _, __):
    """Load the STL mesh into context"""
    mesh = stl.mesh.Mesh.from_file(ctx.files.model_to_preview())
    ctx.mesh = mesh

@internal_action(implied_actions=[load_mesh])
def measure_mesh(ctx: Context, _, __):
    """Calculate mesh metrics from loaded mesh"""
    mesh = ctx.mesh
    max_w, perp_w = calculate_xy_widths(mesh)
    ctx.mesh_metrics = MeshMetrics(
        xrange=(mesh.x.min(), mesh.x.max()),
        yrange=(mesh.y.min(), mesh.y.max()),
        zrange=(mesh.z.min(), mesh.z.max()),
        max_width=max_w,
        perpendicular_width=perp_w,
    )
