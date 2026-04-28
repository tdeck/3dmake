import os
import platform
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import TextIO
from urllib.request import urlopen

from .framework import Context, isolated_action
from utils.bundle_paths import INSTALL_DIR, SCRIPT_BIN_PATH
from utils.update_check import newer_3dmake_version
from version import VERSION

DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


@isolated_action
def self_update(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Download and install the latest version of 3DMake '''

    if not SCRIPT_BIN_PATH.is_relative_to(INSTALL_DIR.parent):
        stdout.write("Self-update is only supported when running an installed version of 3DMake.\n")
        return

    stdout.write("Checking for updates...\n")
    update_info = newer_3dmake_version(ctx.config_dir, VERSION, force_reload=True)

    if update_info is None:
        stdout.write("3DMake is already up to date.\n")
        return

    tty_mode = sys.stdout.isatty()
    new_install_dir = INSTALL_DIR.parent / f'v{update_info.version}'
    new_install_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_path = Path(tmp_dir) / Path(update_info.download_url).name

        # Download
        stdout.write(f"Downloading 3DMake {update_info.version}...\n")
        with urlopen(update_info.download_url) as response:
            total_bytes = int(response.headers.get('Content-Length', 0))
            total_mb = total_bytes // (1024 * 1024)
            downloaded = 0
            last_mb = -1
            with open(archive_path, 'wb') as f:
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    f.write(chunk)
                    downloaded += len(chunk)
                    done_mb = downloaded // (1024 * 1024)
                    if tty_mode and done_mb != last_mb:
                        last_mb = done_mb
                        total_str = f" of {total_mb} MB" if total_mb else ""
                        print(f"\rDownloading... {done_mb} MB{total_str}", end='', flush=True)
        if tty_mode:
            print()

        # Extract
        stdout.write("Extracting...\n")
        is_zip = update_info.download_url.endswith('.zip')
        with (zipfile.ZipFile(archive_path) if is_zip else tarfile.open(archive_path)) as archive:
            if is_zip:
                # Windows zip has files at the top level, no outer dir to unwrap
                members = archive.infolist()
                def do_extract(m): archive.extract(m, new_install_dir)
            else:
                # This extraction unwraps the outer dir (3dmake/) inside the archive
                members = archive.getmembers()
                for m in members:
                    m.name = m.name.split('/', 1)[1] if '/' in m.name else ''
                members = [m for m in members if m.name]
                def do_extract(m): archive.extract(m, new_install_dir, filter='data')

            total = len(members)
            last_pct = -1
            for i, member in enumerate(members):
                do_extract(member)
                if tty_mode:
                    pct = (i + 1) * 100 // total
                    if pct != last_pct and pct % 5 == 0:
                        last_pct = pct
                        print(f"\rExtracting... {pct}%", end='', flush=True)
        if tty_mode:
            print()

    new_bin_path = new_install_dir / SCRIPT_BIN_PATH.name
    if not new_bin_path.exists():
        stdout.write(f"Error: could not find {new_bin_path.name} after extraction.\n")
        return

    if platform.system() != 'Windows':
        new_bin_path.chmod(new_bin_path.stat().st_mode | 0o755)

    stdout.write(f"Running setup for 3DMake {update_info.version}...\n")
    os.execv(str(new_bin_path), [str(new_bin_path), 'setup'])
