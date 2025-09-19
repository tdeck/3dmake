import os
import tempfile
import subprocess
import sys
import re
import shutil
import json
import pytest
import pexpect
from pathlib import Path
from contextlib import contextmanager
from platformdirs import user_config_path
from typing import Any


def test_3dm_setup():
    """Test 3dmake setup with Prusa Mini printer selection"""
    with isolated_3dmake_env() as config_dir:
        print(f"Testing 3dmake setup in: {config_dir}")

        # Start interactive setup
        script_dir = Path(__file__).parent
        cmd = f"{sys.executable} {script_dir / '3dm.py'} setup"

        child = pexpect.spawn(cmd, timeout=30)

        try:
            # Look for printer selection prompt
            child.expect(r'Choose a printer model', timeout=3)
            child.expect(r'Choose an option number', timeout=3)

            # Look for Prusa Mini option and select it
            output_so_far = child.before.decode()
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

            print(child.before.decode()) # TODO debug
            # Verify setup completed successfully
            assert child.exitstatus == 0, f"Setup failed with exit code: {child.exitstatus}"

            # Verify config directory was created
            assert config_dir.exists(), "Config directory should exist after setup"
            defaults_file = config_dir / "defaults.toml"
            assert defaults_file.exists(), "defaults.toml should exist after setup"

        finally:
            child.close()

def test_3dm_build_input_file():
    """Test building a SCAD file to STL"""
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
    """Test slicing an STL file to GCODE"""
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


#
# Utility functions
#
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

        # Set XDG_CONFIG_HOME to point to our temp directory
        # This makes platformdirs.user_config_path('3dmake', None) return temp_dir/3dmake
        old_xdg_config_home = os.environ.get('XDG_CONFIG_HOME')
        os.environ['XDG_CONFIG_HOME'] = str(temp_config_path)

        try:
            # The actual 3dmake config will be at temp_dir/3dmake
            actual_config_dir = temp_config_path / '3dmake'
            yield actual_config_dir
        finally:
            # Restore original environment
            if old_xdg_config_home is not None:
                os.environ['XDG_CONFIG_HOME'] = old_xdg_config_home
            else:
                os.environ.pop('XDG_CONFIG_HOME', None)


def get_config_dir() -> Path:
    """Get the current 3dmake config directory (respects XDG_CONFIG_HOME)"""
    return user_config_path('3dmake', None)


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


