from typing import TextIO
from dataclasses import dataclass

from utils.renderer import VIEWPOINTS, MeshRenderer, ColorScheme
from utils.logging import check_if_value_in_options
from .measure_action import measure_model
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
    implied_actions=[measure_model],
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
