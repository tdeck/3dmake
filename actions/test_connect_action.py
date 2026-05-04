import requests
import ssl
import paho.mqtt.client as mqtt
from threading import Event

from .framework import Context, isolated_action
from utils.ftp import ImplicitFTPS
from utils.output_streams import OutputStream


@isolated_action(needs_options=True)
def test_connect(ctx: Context, stdout: OutputStream, debug_stdout: OutputStream):
    ''' Test connection to the configured print server '''

    mode = ctx.options.print_mode

    if mode == 'octoprint':
        _test_octoprint_connection(ctx, stdout)
    elif mode == 'bambu_lan':
        _test_bambu_connection(ctx, stdout)
    elif mode == 'bambu_connect':
        stdout.write(
            "Cannot test connection in Bambu Connect mode.\n"
            "Launch Bambu Connect to test your printer's connection.\n"
        )
    else:
        raise RuntimeError(f"Unknown print mode '{mode}'")


def _test_octoprint_connection(ctx: Context, stdout: OutputStream):
    """Test OctoPrint connection using the version API endpoint"""

    if not ctx.options.octoprint_host:
        stdout.writeln("ERROR: octoprint_host is not configured")
        return

    if not ctx.options.octoprint_key:
        stdout.writeln("ERROR: octoprint_key is not configured")
        return

    stdout.writeln(f"Host: {ctx.options.octoprint_host}")
    stdout.writeln(f"Testing API connection...")

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
            stdout.writeln(f"SUCCESS: Connected to OctoPrint")
            stdout.writeln(f"  Server version: {version_data.get('server', 'unknown')}")
            stdout.writeln(f"  API version: {version_data.get('api', 'unknown')}")
        elif response.status_code == 401:
            stdout.writeln(f"ERROR: Authentication failed (401)")
            stdout.writeln(f"  Check that your API key is correct")
        elif response.status_code == 403:
            stdout.writeln(f"ERROR: Access forbidden (403)")
            stdout.writeln(f"  Check that your API key has sufficient permissions")
        else:
            stdout.writeln(f"ERROR: Unexpected status code {response.status_code}")
            stdout.writeln(f"  Response: {response.text}")

    except requests.exceptions.ConnectionError as e:
        stdout.writeln(f"ERROR: Could not connect to server")
        stdout.writeln(f"  Check that the host URL is correct and the server is running")
        stdout.writeln(f"  Details: {e}")
    except requests.exceptions.Timeout:
        stdout.writeln(f"ERROR: Connection timed out")
        stdout.writeln(f"  The server took too long to respond")
    except Exception as e:
        stdout.writeln(f"ERROR: {type(e).__name__}: {e}")


def _test_bambu_connection(ctx: Context, stdout: OutputStream):
    """Test Bambu Labs printer connection via FTP and MQTT"""

    if not ctx.options.bambu_host:
        stdout.writeln("ERROR: bambu_host is not configured")
        return

    if not ctx.options.bambu_serial_number:
        stdout.writeln("ERROR: bambu_serial_number is not configured")
        return

    if not ctx.options.bambu_access_code:
        stdout.writeln("ERROR: bambu_access_code is not configured")
        return

    stdout.writeln(f"Host: {ctx.options.bambu_host}")
    stdout.write(f"Serial: {ctx.options.bambu_serial_number}\n\n")

    # Test FTP connection
    stdout.writeln("Testing FTP connection (port 990)...")
    ftp_success = _test_bambu_ftp(ctx, stdout)

    stdout.write("\n")

    # Test MQTT connection
    stdout.writeln("Testing MQTT connection (port 8883)...")
    mqtt_success = _test_bambu_mqtt(ctx, stdout)

    if ftp_success and mqtt_success:
        stdout.write("\nSUCCESS: All Bambu Labs printer connections working\n")
    else:
        stdout.write("\nERROR: Some connections failed\n")


def _test_bambu_ftp(ctx: Context, stdout: OutputStream) -> bool:
    """Test FTP connection to Bambu printer"""
    try:
        ftp_client = ImplicitFTPS()
        ftp_client.connect(host=ctx.options.bambu_host, port=990, timeout=10)
        ftp_client.login(user='bblp', passwd=ctx.options.bambu_access_code)
        ftp_client.prot_p()

        # Try to list directory to verify we can actually interact
        ftp_client.nlst()

        ftp_client.quit()

        stdout.writeln("  FTP: SUCCESS - Connected and authenticated")
        return True

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)

        stdout.writeln(f"  FTP: ERROR - {error_type}")

        if 'authentication' in error_msg.lower() or 'login' in error_msg.lower():
            stdout.writeln(f"    Check that your access code is correct")
        elif 'connection' in error_msg.lower() or 'timed out' in error_msg.lower():
            stdout.writeln(f"    Check that the host IP is correct and printer is on the network")

        stdout.writeln(f"    Details: {error_msg}")
        return False


def _test_bambu_mqtt(ctx: Context, stdout: OutputStream) -> bool:
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
            stdout.writeln("  MQTT: SUCCESS - Connected and authenticated")
            return True
        elif connection_result['error']:
            stdout.writeln(f"  MQTT: ERROR - {connection_result['error']}")
            stdout.writeln(f"    Check that your access code is correct")
            return False
        else:
            stdout.writeln(f"  MQTT: ERROR - Connection timed out")
            stdout.writeln(f"    Check that the host IP is correct and printer is on the network")
            return False

    except Exception as e:
        stdout.writeln(f"  MQTT: ERROR - {type(e).__name__}: {e}")
        return False
