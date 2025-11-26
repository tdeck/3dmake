import requests
from typing import TextIO
import shutil
import hashlib
import zipfile
from pathlib import Path
import ssl
import json
import time

import paho.mqtt.client as mqtt

from .framework import Context, pipeline_action
from .slice_action import slice as slice_model
from utils.bundle_paths import BAMBU_3MF_TEMPLATE_PATH
from utils.ftp import ImplicitFTPS

@pipeline_action(implied_actions=[slice_model])
def print(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Send the sliced model to the printer. '''

    mode = ctx.options.print_mode
    if mode == 'octoprint':
        _print_with_octoprint(ctx, stdout, debug_stdout)
    elif mode == 'bambu_lan':
        _print_with_bambu(ctx, stdout, debug_stdout)
    else:
        raise RuntimeError(f"Unknown print mode '{mode}")


def _print_with_octoprint(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
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


def _print_with_bambu(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    gcode_filename = ctx.files.sliced_gcode.name
    g3mf_filename = f"{gcode_filename}.3mf"

    stdout.write(f"Preparing 3MF file...\n")
    g3mf_path = ctx.files.build_dir / g3mf_filename
    _create_bambu_3mf(ctx.files.sliced_gcode, g3mf_path)

    stdout.write(f"Uploading 3MF to printer...\n")
    _upload_to_bambu_printer(ctx, g3mf_path)

    stdout.write(f"Starting print...\n")
    _start_bambu_print(ctx, g3mf_filename)


def _create_bambu_3mf(gcode_file: Path, output_file: Path) -> None:
    '''
    Embeds the given gcode file in a printable 3mf file compatible with Bambu Labs printers.
    Note that not all the metadata is present or correct in the file; it's just good enough
    to be able to print the GCode.
    '''
    shutil.copy(BAMBU_3MF_TEMPLATE_PATH, output_file)

    gcode_hash = hashlib.md5(open(gcode_file,'rb').read()).hexdigest().upper()

    with zipfile.ZipFile(output_file, 'a') as zf:
        zf.write(gcode_file, 'Metadata/plate_1.gcode', compress_type=zipfile.ZIP_DEFLATED)
        # I'm not absolutely sure if the MD5 is needed, but I'm including it just in case
        zf.writestr('Metadata/plate_1.gcode.md5', gcode_hash)


def _upload_to_bambu_printer(ctx: Context, file: Path) -> None:
    ftp_client = ImplicitFTPS()
    ftp_client.connect(host=ctx.options.bambu_host, port=990)
    ftp_client.login(user='bblp', passwd=ctx.options.bambu_access_code)
    ftp_client.prot_p()

    with open(file, 'rb') as fh:
        ftp_client.storbinary(f"STOR {file.name}", fh)

    ftp_client.quit()


def _start_bambu_print(ctx: Context, filename: str) -> None:
    seq_id = '3dm' + str(int(time.time()))

    def on_connect(client, userdata, flags, rc):
        try:
            if rc != 0:
                raise RuntimeError(f"MQTT connection error: response code {rc}")

            topic = f"device/{ctx.options.bambu_serial_number}/request"
            payload = json.dumps({
                "print": {
                    "sequence_id": seq_id,
                    "command": "project_file",
                    "param": "Metadata/plate_1.gcode",
                    "url": f"ftp://{filename}",
                    "bed_type": "auto",
                    "timelapse": False,
                    "bed_leveling": True,
                    "flow_cali": True,
                    "vibration_cali": True,
                    "layer_inspect": True,
                    "use_ams": False,
                    "ams_mapping": [0],
                    "subtask_name": "",
                    "profile_id": "0",
                    "project_id": "0",
                    "subtask_id": "0",
                    "task_id": "0",
                    "file": ""
                }
            })

            result = client.publish(topic, payload)

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"Failed to send MQTT command: {result}")
        finally:
            client.disconnect()


    client = mqtt.Client(client_id=f"{seq_id}client", protocol=mqtt.MQTTv311)
    client.username_pw_set("bblp", ctx.options.bambu_access_code)

    client.check_hostname = False
    client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    client.on_connect = on_connect

    client.connect(ctx.options.bambu_host, 8883, 60)
    client.loop_forever() # on_connect will disconnect the client after we send our message
