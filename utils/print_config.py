import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

def list_printer_profiles(config_dir: Path)-> List[str]:
    return [
        file_name[:-4] # Strip extension
        for file_name in os.listdir(config_dir / "profiles")
            if file_name.endswith(".ini")  # Filter for INI files
    ]

@dataclass(kw_only=True)
class OverlayName:
    name: str
    profile: Optional[str] # None for default

    def path(self, config_dir: Path) -> Path:
        pdir = self.profile or 'default'
        return config_dir / "overlays" / pdir / f"{self.name}.ini"

    def listing_name(self):
        if self.profile:
            return f"{self.name} for printer {self.profile}"
        else:
            return f"{self.name} for any printer"


def list_overlays(config_dir: Path) -> List[OverlayName]:
    results = []
    for dirpath, _, filenames in os.walk(config_dir / "overlays"):
        dirname = Path(dirpath).name
        if dirname == "default":  # .lower() is just defensive programming
            profile = None
        else:
            profile = dirname

        for filename in filenames:
            if filename.lower().endswith(".ini"):
                results.append(OverlayName(name=filename[:-4], profile=profile))
    return results

