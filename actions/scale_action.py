import numpy as np
from stl import mesh as stl_mesh

from .framework import Context, internal_action
from utils.output_streams import OutputStream

@internal_action
def scale(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    opts = ctx.options
    sx = opts.scale_x or 1.0
    sy = opts.scale_y or 1.0
    sz = opts.scale_z or 1.0

    if sx == 1.0 and sy == 1.0 and sz == 1.0:
        return

    print("\nScaling...")

    ctx.files.scaled_model = ctx.files.build_dir / f"{ctx.files.model.stem}-scaled.stl"

    m = stl_mesh.Mesh.from_file(str(ctx.files.model))
    m.vectors *= np.array([sx, sy, sz])
    m.save(str(ctx.files.scaled_model))
