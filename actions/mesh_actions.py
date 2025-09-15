import stl.mesh

from .framework import Context, internal_action
from coretypes import MeshMetrics # TODO need a better home for this

@internal_action
def load_mesh(ctx: Context, _, __):
    """Load the STL mesh into context"""
    mesh = stl.mesh.Mesh.from_file(ctx.files.model_to_project())
    ctx.mesh = mesh

@internal_action(implied_actions=[load_mesh])
def measure_mesh(ctx: Context, _, __):
    """Calculate mesh metrics from loaded mesh"""
    mesh = ctx.mesh
    ctx.mesh_metrics = MeshMetrics(
        xrange=(mesh.x.min(), mesh.x.max()),
        yrange=(mesh.y.min(), mesh.y.max()),
        zrange=(mesh.z.min(), mesh.z.max()),
    )
