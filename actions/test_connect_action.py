import requests
import ssl
from typing import TextIO
import paho.mqtt.client as mqtt
from threading import Event

from .framework import Context, isolated_action
from utils.ftp import ImplicitFTPS


@isolated_action(needs_options=True)
def test_connect(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Test connection to the configured print server '''

    mode = ctx.options.print_mode
    stdout.write(f"Testing connection to {mode} printer...\n\n")

    if mode == 'octoprint':
        _test_octoprint_connection(ctx, stdout)
    elif mode == 'bambu_lan':
        _test_bambu_connection(ctx, stdout)
    else:
        raise RuntimeError(f"Unknown print mode '{mode}'")


def _test_octoprint_connection(ctx: Context, stdout: TextIO):
    """Test OctoPrint connection using the version API endpoint"""

    if not ctx.options.octoprint_host:
        stdout.write("ERROR: octoprint_host is not configured\n")
        return

    if not ctx.options.octoprint_key:
        stdout.write("ERROR: octoprint_key is not configured\n")
        return

    stdout.write(f"Host: {ctx.options.octoprint_host}\n")
    stdout.write(f"Testing API connection...\n")

    try:
        # Test the version endpoint - simple read-only check
        response = requests.get(
            f"{ctx.options.octoprint_host}/api/version",
            headers={
                'X-Api-Key': ctx.options.octoprint_key,
            },
            timeout=10,
            verify=False,  # Allow self-signed certificates
        )

        if response.status_code == 200:
            version_data = response.json()
            stdout.write(f"SUCCESS: Connected to OctoPrint\n")
            stdout.write(f"  Server version: {version_data.get('server', 'unknown')}\n")
            stdout.write(f"  API version: {version_data.get('api', 'unknown')}\n")
        elif response.status_code == 401:
            stdout.write(f"ERROR: Authentication failed (401)\n")
            stdout.write(f"  Check that your API key is correct\n")
        elif response.status_code == 403:
            stdout.write(f"ERROR: Access forbidden (403)\n")
            stdout.write(f"  Check that your API key has sufficient permissions\n")
        else:
            stdout.write(f"ERROR: Unexpected status code {response.status_code}\n")
            stdout.write(f"  Response: {response.text}\n")

    except requests.exceptions.ConnectionError as e:
        stdout.write(f"ERROR: Could not connect to server\n")
        stdout.write(f"  Check that the host URL is correct and the server is running\n")
        stdout.write(f"  Details: {e}\n")
    except requests.exceptions.Timeout:
        stdout.write(f"ERROR: Connection timed out\n")
        stdout.write(f"  The server took too long to respond\n")
    except Exception as e:
        stdout.write(f"ERROR: {type(e).__name__}: {e}\n")


def _test_bambu_connection(ctx: Context, stdout: TextIO):
    """Test Bambu Labs printer connection via FTP and MQTT"""

    if not ctx.options.bambu_host:
        stdout.write("ERROR: bambu_host is not configured\n")
        return

    if not ctx.options.bambu_serial_number:
        stdout.write("ERROR: bambu_serial_number is not configured\n")
        return

    if not ctx.options.bambu_access_code:
        stdout.write("ERROR: bambu_access_code is not configured\n")
        return

    stdout.write(f"Host: {ctx.options.bambu_host}\n")
    stdout.write(f"Serial: {ctx.options.bambu_serial_number}\n\n")

    # Test FTP connection
    stdout.write("Testing FTP connection (port 990)...\n")
    ftp_success = _test_bambu_ftp(ctx, stdout)

    stdout.write("\n")

    # Test MQTT connection
    stdout.write("Testing MQTT connection (port 8883)...\n")
    mqtt_success = _test_bambu_mqtt(ctx, stdout)

    if ftp_success and mqtt_success:
        stdout.write("\nSUCCESS: All Bambu Labs printer connections working\n")
    else:
        stdout.write("\nERROR: Some connections failed\n")


def _test_bambu_ftp(ctx: Context, stdout: TextIO) -> bool:
    """Test FTP connection to Bambu printer"""
    try:
        ftp_client = ImplicitFTPS()
        ftp_client.connect(host=ctx.options.bambu_host, port=990, timeout=10)
        ftp_client.login(user='bblp', passwd=ctx.options.bambu_access_code)
        ftp_client.prot_p()

        # Try to list directory to verify we can actually interact
        ftp_client.nlst()

        ftp_client.quit()

        stdout.write("  FTP: SUCCESS - Connected and authenticated\n")
        return True

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)

        stdout.write(f"  FTP: ERROR - {error_type}\n")

        if 'authentication' in error_msg.lower() or 'login' in error_msg.lower():
            stdout.write(f"    Check that your access code is correct\n")
        elif 'connection' in error_msg.lower() or 'timed out' in error_msg.lower():
            stdout.write(f"    Check that the host IP is correct and printer is on the network\n")

        stdout.write(f"    Details: {error_msg}\n")
        return False


def _test_bambu_mqtt(ctx: Context, stdout: TextIO) -> bool:
    """Test MQTT connection to Bambu printer"""

    connection_result = {'success': False, 'error': None}
    connect_event = Event()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            connection_result['success'] = True
        else:
            connection_result['error'] = f"Connection failed with code {rc}"
        connect_event.set()
        client.disconnect()

    try:
        client = mqtt.Client(client_id="3dm_test_client", protocol=mqtt.MQTTv311)
        client.username_pw_set("bblp", ctx.options.bambu_access_code)

        client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

        client.on_connect = on_connect

        client.connect(ctx.options.bambu_host, 8883, 60)
        client.loop_start()

        # Wait up to 10 seconds for connection
        connect_event.wait(timeout=10)
        client.loop_stop()

        if connection_result['success']:
            stdout.write("  MQTT: SUCCESS - Connected and authenticated\n")
            return True
        elif connection_result['error']:
            stdout.write(f"  MQTT: ERROR - {connection_result['error']}\n")
            stdout.write(f"    Check that your access code is correct\n")
            return False
        else:
            stdout.write(f"  MQTT: ERROR - Connection timed out\n")
            stdout.write(f"    Check that the host IP is correct and printer is on the network\n")
            return False

    except Exception as e:
        stdout.write(f"  MQTT: ERROR - {type(e).__name__}: {e}\n")
        return False
