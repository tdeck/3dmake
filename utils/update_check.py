"""
Checks for newer versions of 3dmake.
"""

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import urlopen
from urllib.error import URLError
from typing import Optional
from packaging.version import Version, InvalidVersion

UPDATE_CHECK_INTERVAL = timedelta(hours=24)
FETCH_TIMEOUT_S = 2
VERSION_CHECK_URL = "https://blindmakers.net/3dmake_version.json"
UPDATE_CACHE_FILE = "update_check.json"


@dataclass
class UpdateInfo:
    version: str
    download_url: str


def newer_3dmake_version(
    config_dir: Path,
    current_version: str,
    force_reload: bool = False,
) -> Optional[UpdateInfo]:
    """
    Check if a newer version of 3dmake is available.

    Returns an UpdateInfo if a newer version is available, None otherwise.
    """
    cache_file = config_dir / UPDATE_CACHE_FILE
    server_update_info = None

    try:
        if not force_reload and cache_file.exists():
            cached = json.loads(cache_file.read_text())
            cache_age = datetime.now() - datetime.fromisoformat(cached.get('last_check', ''))
            if cache_age < UPDATE_CHECK_INTERVAL:
                server_update_info = cached

        if server_update_info is None:
            with urlopen(f"{VERSION_CHECK_URL}?current={current_version}", timeout=FETCH_TIMEOUT_S) as response:
                server_update_info = json.loads(response.read().decode('utf-8'))
            config_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(
                    server_update_info | {'last_check': datetime.now().isoformat()},
                    indent=2,
                )
            )

        latest_version = server_update_info.get('latest_version')
        download_url = server_update_info.get('platform_releases', {}).get(platform.system())
        if latest_version and download_url and Version(latest_version) > Version(current_version):
            return UpdateInfo(latest_version, download_url)
    except Exception:
        pass

    return None
