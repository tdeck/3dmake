import requests
from typing import TextIO

from .framework import Context, pipeline_action
from .slice_action import slice as slice_model

@pipeline_action(implied_actions=[slice_model])
def print(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Send the sliced model to OctoPrint '''

    if not ctx.options.octoprint_host or not ctx.options.octoprint_key:
        raise RuntimeError("Either octoprint_host or octoprint_key is not configured.")

    server_filename = ctx.files.sliced_gcode.name
    with open(ctx.files.sliced_gcode, 'rb') as fh:
        response = requests.post(
            f"{ctx.options.octoprint_host}/api/files/local", # TODO folder
            headers={
                'X-Api-Key': ctx.options.octoprint_key,
            },
            files={
                'file': (server_filename, fh, 'application/octet-stream'),
            },
            data={
                'select': True,
                'print': ctx.options.auto_start_prints,
            },
            verify=False, # This is needed for self-signed local servers
        )

    # TODO handle this better
    if response.status_code == 201:
        stdout.write(f"File uploaded successfully as {server_filename}\n")
    else:
        stdout.write(f"Failed to upload. Status code: {response.status_code}\n")
        stdout.write(response.text or '')
        stdout.write("\n")
