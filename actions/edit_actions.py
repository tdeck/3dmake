import subprocess

from utils.editor import choose_editor
from .framework import Context, isolated_action

@isolated_action(needs_options=True)
def edit_model(ctx: Context, _, __): # TODO
    print(ctx.files)
    subprocess.run([choose_editor(ctx.options), ctx.files.scad_source])
