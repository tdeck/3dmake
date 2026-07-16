import json
import tomllib
from pathlib import Path
from typing import Any, Dict


def load_global_settings(config_dir: Path) -> Dict[str, Any]:
    """Load settings from the global defaults.toml, if it exists"""
    defaults_toml = config_dir / "defaults.toml"
    if defaults_toml.exists():
        with open(defaults_toml, 'rb') as fh:
            return tomllib.load(fh)
    return {}


def save_global_settings(config_dir: Path, settings: Dict[str, Any]) -> None:
    """Overwrite the global defaults.toml with the given settings"""
    defaults_toml = config_dir / "defaults.toml"
    # TODO write this properly; it's brittle
    with open(defaults_toml, 'w') as fh:
        for k, v in settings.items():
            fh.write(f"{k} = {json.dumps(v)}\n")
