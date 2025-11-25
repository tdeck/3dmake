from typing import TextIO
from dataclasses import dataclass
from pathlib import Path

from utils.renderer import VIEWPOINTS, MeshRenderer, ColorScheme
from utils.logging import check_if_value_in_options
from .mesh_actions import load_mesh
from .framework import Context, pipeline_action

WIDTH = 1080
HEIGHT = 720

COLORSCHEMES = {
    'slicer_light': ColorScheme('orange', '#ccc', 'green', 'blue'),
    'slicer_dark': ColorScheme('orange', '#222', 'green', 'blue'),
    'light_on_dark': ColorScheme('floralwhite', '#333', 'darkgray', 'darkgray'),
}

@pipeline_action(
    gerund='imaging',
    last_in_chain=True,
    implied_actions=[load_mesh],
)
def image(ctx: Context, stdout: TextIO, __):
    ''' Exports one or more rendered images of the model '''
    # Check arguments
    check_if_value_in_options('color scheme', ctx.options.colorscheme, COLORSCHEMES)
    for angle in ctx.options.image_angles:
        check_if_value_in_options('viewpoint angle', angle, VIEWPOINTS)

    renderer = MeshRenderer(ctx.mesh, colors=COLORSCHEMES[ctx.options.colorscheme])

    for angle in ctx.options.image_angles:
        # TODO support explicitly specifying angles and things
        viewpoint = VIEWPOINTS[angle]

        filename = ctx.files.build_dir / f"{ctx.files.model_to_slice().stem}-{angle}.png"
        img = renderer.get_image(viewpoint, WIDTH, HEIGHT)
        with open(filename , 'wb') as fh:
            img.save(fh, format="png")

        ctx.files.rendered_images[angle] = filename

    # Print the generated image paths (but not in single-file mode, where 3dm.py will handle it)
    if not ctx.single_file_mode:
        cwd = Path.cwd()
        image_files = list(ctx.files.rendered_images.values())

        # Convert to relative paths if inside working directory
        display_paths = []
        for file in image_files:
            if file.is_relative_to(cwd):
                display_paths.append(file.relative_to(cwd))
            else:
                display_paths.append(file)

        if len(display_paths) == 1:
            stdout.write(f"Image saved to {display_paths[0]}\n")
        else:
            stdout.write(f"Images saved:\n")
            for path in display_paths:
                stdout.write(f"    {path}\n")
