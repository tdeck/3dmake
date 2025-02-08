import threading

from .framework import Context, pipeline_action

@pipeline_action(gerund='auto-orienting')
def orient(ctx: Context, _, __):
    ''' Auto-orient the model to minimize support '''
    from tweaker3 import MeshTweaker, FileHandler  # Slow import

    ctx.files.oriented_model = ctx.files.build_dir / f"{ctx.files.model.stem}-oriented.stl"

    # This was basically copied from Tweaker.py since it doesn't have a code-based interface
    # to handle all meshes at once
    file_handler = FileHandler.FileHandler()
    mesh_objects = file_handler.load_mesh(ctx.files.model)
    info = {}  # This is what Tweaker calls this; it needs a better name
    for part, content in mesh_objects.items():
        tweak_res = MeshTweaker.Tweak(
            content['mesh'],
            extended_mode=True,
            verbose=False,
            show_progress=False,
        )
        info[part] = dict(matrix=tweak_res.matrix, tweaker_stats=tweak_res)

        file_handler.write_mesh(mesh_objects, info, ctx.files.oriented_model, 'binarystl')
