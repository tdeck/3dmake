import os
from pathlib import Path
from typing import Iterable, Iterator, List, Optional
from dataclasses import dataclass, field

def list_printer_profiles(config_dir: Path)-> List[str]:
    return sorted([
        file_name[:-4] # Strip extension
        for file_name in os.listdir(config_dir / "profiles")
            if file_name.endswith(".ini")
    ])

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
    return sorted(results, key=lambda o: (o.name, o.profile or ''))


def write_overlay_file(path: Path, values: dict[str, str]) -> None:
    ''' Writes a flat key/value overlay .ini file - the same format read_config_values
    and resolve_overlay_path (when given a path directly) expect. '''
    with open(path, 'w') as fh:
        for key, value in values.items():
            fh.write(f"{key} = {value}\n")


def read_config_values(ini_files: list[Path]) -> dict[str, str]:
    result = {}
    for path in ini_files:
        with open(path, 'r') as fh:
            for line in fh:
                trimmed = line.strip()
                if not trimmed:
                    continue
                if trimmed[0] == '#' or trimmed[0] == ';':
                    continue # Comment
                k, v = trimmed.split('=', 1)
                result[k.strip()] = v.strip()

    return result

@dataclass(kw_only=True)
class ProfileConfig:
    # category name -> {key: value}. Keys are assumed unique across categories.
    by_category: dict[str, dict[str, str]] = field(default_factory=dict)
    # key -> name of the last overlay that set it. Keys with no entry here
    # come from the base profile only.
    overlay_sources: dict[str, str] = field(default_factory=dict)

    def flattened(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for category_values in self.by_category.values():
            result.update(category_values)
        return result

    def __getitem__(self, key: str) -> str:
        return self.flattened()[key]

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.flattened().get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.flattened()

    def overlay_source(self, key: str) -> Optional[str]:
        """Name of the last overlay that set this key, or None if it was never overlaid."""
        return self.overlay_sources.get(key)


def resolve_profile_path(config_dir: Path, profile: str) -> Path:
    ''' profile may be a bare profile name (resolved under config_dir/profiles/) or
    a path to an existing .ini file, which is used directly if it exists. '''
    candidate = Path(profile)
    if candidate.is_file():
        return candidate
    return config_dir / "profiles" / f"{profile}.ini"


def resolve_overlay_path(config_dir: Path, profile: str, overlay: str) -> Path:
    ''' overlay may be a bare overlay name (resolved under config_dir/overlays/,
    preferring a profile-specific version) or a path to an existing .ini file,
    which is used directly if it exists. '''
    overlay_candidate = Path(overlay)
    if overlay_candidate.is_file():
        return overlay_candidate

    overlays_dir = config_dir / "overlays"
    default_path = overlays_dir / "default" / f"{overlay}.ini"

    # A profile-specific override only makes sense when profile is a name
    # (matching an overlays/<name>/ directory) - if profile is itself a path,
    # there's no name to match against, so fall straight through to default.
    if not Path(profile).is_file():
        profile_specific_path = overlays_dir / profile / f"{overlay}.ini"
        if profile_specific_path.exists():
            return profile_specific_path

    if default_path.exists():
        return default_path
    raise RuntimeError(f"Could not find overlay '{overlay}' for profile '{profile}'")


def read_profile_config(config_dir: Path, profile_name: str, overlays: Optional[List[str]] = None) -> ProfileConfig:
    path = resolve_profile_path(config_dir, profile_name)

    by_category: dict[str, dict[str, str]] = {}
    category_by_key: dict[str, str] = {}
    overlay_sources: dict[str, str] = {}
    current_category = ""

    with open(path, 'r') as fh:
        for line in fh:
            trimmed = line.strip()
            if not trimmed:
                continue
            if trimmed.startswith('##'):
                current_category = trimmed.lstrip('#').strip().rstrip(':').strip()
                continue
            if trimmed[0] == '#' or trimmed[0] == ';':
                continue # Comment
            k, v = trimmed.split('=', 1)
            k, v = k.strip(), v.strip()
            by_category.setdefault(current_category, {})[k] = v
            category_by_key[k] = current_category

    # Overlay files are flat, uncategorized key/value lists. Slot each overlaid
    # value into whichever category the base profile already put that key in,
    # so overlays can't reshuffle the profile's category structure.
    for overlay_name in (overlays or []):
        overlay_path = resolve_overlay_path(config_dir, profile_name, overlay_name)
        for k, v in read_config_values([overlay_path]).items():
            category = category_by_key.setdefault(k, "")
            by_category.setdefault(category, {})[k] = v
            overlay_sources[k] = overlay_name

    return ProfileConfig(by_category=by_category, overlay_sources=overlay_sources)
