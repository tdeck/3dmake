import textwrap
from typing import TextIO

from .framework import Context, isolated_action

@isolated_action
def help(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Display this message ''' # This docstring is used to produce the help

    # We can't do this at the top level or we'll get a circular import and break
    from . import ALL_ACTIONS_IN_ORDER

    max_action_length = max((len(a.name) for a in ALL_ACTIONS_IN_ORDER.values() if not a.internal))

    action_descriptions = "\n".join([
        f"    {a.name:<{max_action_length}}  {a.doc}"
        for a in ALL_ACTIONS_IN_ORDER.values() if not a.internal
    ])

    stdout.write(textwrap.dedent('''\
        Usage: 3dm ACTIONS... [OPTIONS]... [INPUT_FILE]

        Examples:
            3dm build
            3dm build orient slice
            3dm build orient slice --model cover --overlay supports
            3dm info alpaca.stl
            3dm preview alpaca.stl
            3dm slice print alpaca.stl

        Actions:
        {action_descriptions}

        Options:
            --scale 1.0         Scale by a decimal factor
            --model NAME        Choose a model in a multi-model project
            --profile NAME      Select a printer profile
            --overlay NAME      Apply an overlay to slicer settings; can be used multiple times
            --view NAME         The type of preivew to produce, see the documentation for more info
            --angle NAME        The viewpoint (e.g. "top") used for an image export, can be used multiple times
            --copies NUM        Number of copies to print (default: 1)
            --interactive       For 3dm info, start an interactive chat with the AI
            --colorscheme NAME  The name of the color used for an image export (short name)
            --image-size WxH    Image dimensions in pixels (e.g., 1920x1080, default: 1080x720)

        Most options can be abbreviated as one letter with a single dash (e.g. -s 50% to scale)
    ''').format(action_descriptions=action_descriptions))
