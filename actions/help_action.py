import textwrap
from typing import TextIO

from .framework import Context, isolated_action

@isolated_action
def help(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
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
            setup               Set up 3dmake for the first time, or overwrite existing settings
            new                 Create a new 3dmake project directory structure
            build               Build the OpenSCAD model and produce an STL file
            info                Get basic dimensional info about the model, and AI description if enabled
            orient              Auto-orient the model to minimize support
            preview             Produce a 2-D representation of the object
            slice               Slice the model and produce a printable gcode file
            print               Send the sliced model to OctoPrint
            edit-model          Open model SCAD file in your editor (affected by -m)
            edit-overlay        Open an overlay file in your editor (affected by -o)
            edit-profile        Open printer profile in your editor (affected by -p)
            edit-global-config  Edit 3DMake user settings file (default printer, API keys, etc...)
            help                Display this message
            version             Print the 3dmake version and paths

        Options:
            --scale 1.0     Scale by a decimal factor
            --model NAME    Choose a model in a multi-model project
            --profile NAME  Select a printer profile
            --overlay NAME  Apply an overlay to slicer settings; can be used multiple times
            --view NAME     The type of preivew to produce, see the documentation for more info

        Each option can be abbreviated as one letter with a single dash (e.g. -s 50% to scale)
    '''))
