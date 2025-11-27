import os
import tempfile
import subprocess
import sys
import re
import shutil
import json
import pytest
import pexpect
from pexpect.popen_spawn import PopenSpawn
from pathlib import Path
from contextlib import contextmanager
from platformdirs import user_config_path
from typing import Any
from unittest.mock import patch
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket


def test_3dm_setup():
    with isolated_3dmake_env() as config_dir:
        print(f"Testing 3dmake setup in: {config_dir}")

        # Start interactive setup
        script_dir = Path(__file__).parent
        cmd = [sys.executable, str(script_dir / '3dm.py'), 'setup']

        child = PopenSpawn(cmd, timeout=30, encoding='utf-8')

        # Look for printer selection prompt
        child.expect(r'Choose a printer model', timeout=3)
        child.expect(r'Choose an option number', timeout=3)

        # Look for Prusa Mini option and select it
        output_so_far = child.before
        print("Printer selection prompt received")

        # Find which number corresponds to Prusa Mini
        lines = output_so_far.split('\n')
        mini_option = None
        for line in lines:
            match = re.search(r'(\d+): prusa mini', line, re.IGNORECASE)
            if match:
                mini_option = match.group(1)
                break

        assert mini_option, f"Option for prusa mini not found. Options:\n{output_so_far}"
        child.sendline(mini_option)

        # Skip Gemini setup
        child.expect(r'Do you want to.*Gemini', timeout=10)
        child.sendline('n')

        # Skip OctoPrint setup
        child.expect(r'Do you want to.*OctoPrint', timeout=10)
        child.sendline('n')

        # Wait for completion
        child.expect(pexpect.EOF, timeout=10)

        # Ensure process has terminated and exit status is available
        child.wait()

        print(child.before) # TODO debug
        # Verify setup completed successfully
        assert child.exitstatus == 0, f"Setup failed with exit code: {child.exitstatus}"

        # Verify config directory was created
        assert config_dir.exists(), "Config directory should exist after setup"
        defaults_file = config_dir / "defaults.toml"
        assert defaults_file.exists(), "defaults.toml should exist after setup"


def test_3dm_new():
    with isolated_3dmake_env() as config_dir:
        populate_config()

        with tempfile.TemporaryDirectory() as work_dir:
            work_path = Path(work_dir)

            script_dir = Path(__file__).parent
            cmd = [sys.executable, str(script_dir / '3dm.py'), 'new']

            child = PopenSpawn(cmd, cwd=str(work_path), timeout=30, encoding='utf-8')

            child.expect(r'Choose a project directory name', timeout=3)
            child.sendline('test_project')

            child.expect(pexpect.EOF, timeout=10)
            child.wait()

            assert child.exitstatus == 0, f"New command failed with exit code: {child.exitstatus}"

            project_path = work_path / "test_project"
            expected_files = [
                "3dmake.toml",
                "src/main.scad",
                "build/",
            ]

            for expected_file in expected_files:
                file_path = project_path / expected_file
                assert file_path.exists(), f"Expected file not created: {file_path}"
                if file_path.is_file():
                    assert file_path.stat().st_size > 0, f"File is empty: {file_path}"


def test_3dm_build_input_file():
    with isolated_3dmake_env() as config_dir:
        # Set up configuration
        populate_config()

        with tempfile.TemporaryDirectory() as work_dir:
            work_path = Path(work_dir)
            test_scad = Path(__file__).parent / "tests" / "pyramid.scad"

            result = run_3dmake(['build', str(test_scad)], cwd=work_path)

            # Check that build succeeded
            assert result.returncode == 0, f"Build failed: {result.stderr}"

            # Check that STL file was created
            expected_stl = work_path / "pyramid.stl"
            assert expected_stl.exists(), f"STL file not created at {expected_stl}"

            # Verify STL file has content
            assert expected_stl.stat().st_size > 0, "STL file is empty"


def test_3dm_slice_input_file():
    with isolated_3dmake_env() as config_dir:
        # Set up configuration
        populate_config()

        # Create temporary working directory
        with tempfile.TemporaryDirectory() as work_dir:
            work_path = Path(work_dir)
            test_stl = Path(__file__).parent / "tests" / "hexagon.stl"

            result = run_3dmake(['slice', str(test_stl)], cwd=work_path)

            # Check that slice succeeded
            assert result.returncode == 0, f"Slice failed: {result.stderr}"

            # Check that GCODE file was created
            expected_gcode = work_path / "hexagon.gcode"
            assert expected_gcode.exists(), f"GCODE file not created at {expected_gcode}"

            # Verify GCODE file has content
            assert expected_gcode.stat().st_size > 0, "GCODE file is empty"


def test_3dm_info_input_file():
    gemini_key = os.environ.get('GEMINI_TEST_KEY')
    settings = {}
    if gemini_key:
        settings['gemini_key'] = gemini_key

    with isolated_3dmake_env() as config_dir:
        # Set up configuration
        populate_config(settings)

        with tempfile.TemporaryDirectory() as work_dir:
            work_path = Path(work_dir)
            stl_path = Path(__file__).parent / "tests" / "hexagon.stl"

            result = run_3dmake(['info', str(stl_path)], cwd=work_path)
            assert result.returncode == 0

            assert "Mesh size: x=20.00, y=17.32, z=20.00" in result.stdout
            assert "Mesh center: x=0.00, y=0.00, z=10.00" in result.stdout

            if gemini_key:
                assert "AI description:" in result.stdout
                # Should have some actual description text after the header
                # Even the dumb model should identify this as a hexagon
                assert "hexagon" in result.stdout
            else:
                pytest.skip('No GEMINI_TEST_KEY env var - skipping full test of 3dm info')


def test_3dm_orient_input_file():
    with isolated_3dmake_env() as config_dir:
        populate_config()

        with tempfile.TemporaryDirectory() as work_dir:
            work_path = Path(work_dir)
            test_stl = Path(__file__).parent / "tests" / "inverted_pyramid.stl"
            expected_oriented_stl = Path(__file__).parent / "tests" / "inverted_pyramid-oriented.stl"

            result = run_3dmake(['orient', str(test_stl)], cwd=work_path)

            assert result.returncode == 0, f"Orient failed: {result.stderr}"

            output_stl = work_path / "inverted_pyramid-oriented.stl"
            assert output_stl.exists(), f"Oriented STL file not created at {output_stl}"

            assert_stl_vertices_close(output_stl, expected_oriented_stl)


def test_3dm_build_slice_print_input_file():
    # This also slices the input file
    with mock_octoprint_server() as port:
        with isolated_3dmake_env() as config_dir:
            populate_config({
                'octoprint_host': f'http://localhost:{port}',
                'octoprint_key': 'test_api_key',
            })

            with tempfile.TemporaryDirectory() as work_dir:
                work_path = Path(work_dir)
                test_stl = Path(__file__).parent / "tests" / "pyramid.scad"

                result = run_3dmake(['print', str(test_stl)], cwd=work_path)

                assert result.returncode == 0, f"Print failed: {result.stderr}"
                assert "Building..." in result.stdout
                assert "Slicing..." in result.stdout
                assert "File uploaded successfully" in result.stdout


def test_3dm_edit_model():
    with isolated_3dmake_env() as config_dir:
        populate_config()

        with tempfile.TemporaryDirectory() as work_dir:
            work_path = Path(work_dir)
            setup_sample_project(work_path)

            result = run_3dmake(['edit-model'], cwd=work_path)

            assert result.returncode == 0, f"Edit failed: {result.stderr}"
            match = re.match(r'LAUNCH EDITOR.*src[\\/]main.scad', result.stdout)
            assert match, f"Expected LAUNCH EDITOR not found in '{result.stdout}'"


def test_library_dependencies():
    with isolated_3dmake_env() as config_dir:
        populate_config()

        with tempfile.TemporaryDirectory() as work_dir:
            print(f"Working dir {work_dir}")
            work_path = Path(work_dir)
            setup_sample_project(work_path)

            result = run_3dmake(['install-libraries'], cwd=work_path)
            assert result.returncode == 0
            assert 'Downloading bosl' in result.stdout
            assert 'Extracting library' in result.stdout

            result = run_3dmake(['build'], cwd=work_path)
            assert result.returncode == 0
            assert 'Building...' in result.stdout
            assert work_path.joinpath("build/main.stl").exists()

#
# Utility functions
#
def setup_sample_project(work_dir: Path):
    """Copy the sample project contents from tests/sample_project to work_dir"""
    sample_project_src = Path(__file__).parent / "tests" / "sample_project"
    shutil.copytree(sample_project_src, work_dir, dirs_exist_ok=True)


def assert_stl_vertices_close(stl_path1: Path, stl_path2: Path, delta: float = 1e-6):
    from stl import mesh
    import numpy as np

    mesh1 = mesh.Mesh.from_file(str(stl_path1))
    mesh2 = mesh.Mesh.from_file(str(stl_path2))

    vertices1 = mesh1.vectors.reshape(-1, 3)
    vertices2 = mesh2.vectors.reshape(-1, 3)

    assert len(vertices1) == len(vertices2), f"Vertex count mismatch: {len(vertices1)} vs {len(vertices2)}"

    vertices1_sorted = vertices1[np.lexsort((vertices1[:, 2], vertices1[:, 1], vertices1[:, 0]))]
    vertices2_sorted = vertices2[np.lexsort((vertices2[:, 2], vertices2[:, 1], vertices2[:, 0]))]

    assert np.allclose(vertices1_sorted, vertices2_sorted, atol=delta), "STL vertices do not match within tolerance"


class MockOctoPrintHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/files/local':
            api_key = self.headers.get('X-Api-Key')
            if api_key == 'test_api_key':
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {"files": {"local": {"name": "test.gcode", "path": "test.gcode"}}}
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(401)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@contextmanager
def mock_octoprint_server():
    # Use port 0 to automatically select a free port
    server = HTTPServer(('localhost', 0), MockOctoPrintHandler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    time.sleep(0.1)

    try:
        yield port
    finally:
        server.shutdown()
        thread.join(timeout=1)


@contextmanager
def isolated_3dmake_env():
    """
    Context manager that creates a temporary directory and sets up environment
    variables so that 3dmake uses it as the global config directory.

    Usage:
        with isolated_3dmake_env() as temp_config_dir:
            # Run 3dmake commands here
            result = subprocess.run(['python3', '3dm.py', 'help'])
    """
    # Create temporary directory for config
    with tempfile.TemporaryDirectory(prefix='3dmake_test_') as temp_dir:
        temp_config_path = Path(temp_dir)
        print(f"Temporary 3dmake config dir: {temp_config_path}")

        old_3dmake_config_dir = os.environ.get('3DMAKE_CONFIG_DIR')

        actual_config_dir = temp_config_path / '3dmake'
        os.environ['3DMAKE_CONFIG_DIR'] = str(actual_config_dir)

        try:
            yield actual_config_dir
        finally:
            if old_3dmake_config_dir is not None:
                os.environ['3DMAKE_CONFIG_DIR'] = old_3dmake_config_dir
            else:
                os.environ.pop('3DMAKE_CONFIG_DIR', None)


def get_config_dir() -> Path:
    """Get the current 3dmake config directory"""
    return Path(os.environ['3DMAKE_CONFIG_DIR']) if '3DMAKE_CONFIG_DIR' in os.environ else user_config_path('3dmake', None)


def populate_config(overrides: dict[str, Any] = {}) -> dict[str, Any]:
    """ This must be called within a isolated_3dmake_env() block. Returns populated settings. """
    # Get the config directory (should be our isolated temp dir)
    config_dir = get_config_dir()
    script_dir = Path(__file__).parent
    default_config_dir = script_dir / 'default_config'

    # Copy over profiles, overlays, templates, and other config files
    shutil.copytree(
        default_config_dir,
        config_dir,
        dirs_exist_ok=True
    )

    # Create minimal defaults.toml with sane defaults
    defaults_toml = config_dir / "defaults.toml"
    minimal_settings = {
        'view': '3sil',
        'model_name': 'main',
        'auto_start_prints': False,  # Don't auto-start in tests
        'printer_profile': 'prusa_mini',  # Use a common profile for testing
        'llm_name': 'gemini-2.5-flash-lite',
        'editor': 'echo LAUNCH EDITOR',
    }
    minimal_settings.update(overrides)

    with open(defaults_toml, 'w') as fh:
        for key, value in minimal_settings.items():
            fh.write(f"{key} = {json.dumps(value)}\n")
    return minimal_settings


def run_3dmake(args, cwd=None) -> subprocess.CompletedProcess:
    """
    Helper function to run 3dmake with the given arguments.
    """
    script_dir = Path(__file__).parent
    cmd = [sys.executable, str(script_dir / '3dm.py')] + args

    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )


