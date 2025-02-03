import stl.mesh

from .framework import Context, internal_action
from coretypes import MeshMetrics # TODO need a better home for this

@internal_action
def measure_model(ctx: Context, _, __):
    mesh = stl.mesh.Mesh.from_file(ctx.files.model_to_project())
    ctx.mesh = mesh
    ctx.mesh_metrics = MeshMetrics(
        xrange=(mesh.x.min(), mesh.x.max()),
        yrange=(mesh.y.min(), mesh.y.max()),
        zrange=(mesh.z.min(), mesh.z.max()),
    )
