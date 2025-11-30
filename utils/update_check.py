"""
Checks for newer versions of 3dmake.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import urlopen
from urllib.error import URLError
from typing import Optional
from packaging.version import Version, InvalidVersion

UPDATE_CHECK_INTERVAL = timedelta(hours=24)
FETCH_TIMEOUT_S = 2
VERSION_CHECK_URL = "https://blindmakers.net/3dmake_version.json"
DOWNLOAD_URL = "https://blindmakers.net/3dmake"
UPDATE_CACHE_FILE = "update_check.json"


def _fetch_latest_version(current_version: str) -> Optional[str]:
    """Fetch the latest version from the remote URL."""
    url = f"{VERSION_CHECK_URL}?current={current_version}"
    try:
        with urlopen(url, timeout=FETCH_TIMEOUT_S) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('latest_version')
    except (URLError, json.JSONDecodeError, KeyError, TimeoutError):
        return None


def newer_3dmake_version(config_dir: Path, current_version: str) -> Optional[str]:
    """
    Check if a newer version of 3dmake is available.

    Returns the newer version string if available, None otherwise.
    """
    cache_file = config_dir / UPDATE_CACHE_FILE
    now = datetime.now()

    cached_data = {}
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            cached_data = {}

    should_fetch = True
    last_check_str = cached_data.get('last_check')
    if last_check_str:
        try:
            last_check = datetime.fromisoformat(last_check_str)
            if now - last_check < UPDATE_CHECK_INTERVAL:
                should_fetch = False
        except (ValueError, TypeError):
            pass

    if should_fetch:
        latest_version = _fetch_latest_version(current_version)
        cached_data['last_check'] = now.isoformat()

        if latest_version:
            cached_data['latest_version'] = latest_version

        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(cached_data, f, indent=2)
        except IOError:
            pass

    latest_version = cached_data.get('latest_version')
    if not latest_version:
        return None

    try:
        if Version(latest_version) > Version(current_version):
            return latest_version
    except InvalidVersion:
        pass

    return None
