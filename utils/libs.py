import json
from typing import TextIO, Optional
from pathlib import Path
from dataclasses import dataclass
from packaging.version import Version
import tomllib

CATALOG_FILE = 'library_catalog.toml'
INSTALLED_LIBS_FILE = 'installed_libraries.json'

# TODO make lookup of libraries in catalog and registry case-insensitive

@dataclass(kw_only=True)
class CatalogLibraryVersion:
    version: Version
    archive: str  # A URL
    subdir: Optional[str] = None

@dataclass(kw_only=True)
class CatalogLibrary:
    name: str
    full_name: str
    versions: list[CatalogLibraryVersion]
    license: str
    homepage: str

    def latest_version(self) -> CatalogLibraryVersion:
        return max(self.versions, key=lambda v: v.version)

class LibraryCatalog:
    libs: dict[str, CatalogLibrary]

@dataclass(kw_only=True)
class InstalledLib:
    name: str
    version_dirs: dict[Version, Path]

    def latest_version_dir(self) -> Path:
        # This uses the nice property of Version objects that they're hashable and comparable
        return self.version_dirs[max(self.version_dirs)]

    def latest_version(self) -> Version:
        return max(self.version_dirs)

    
class InstalledLibRegistry:
    libs: dict[str, InstalledLib] = {}

    @staticmethod
    def read_json(fh: TextIO) -> 'InstalledLibRegistry':
        res = InstalledLibRegistry()
        raw_dicts = json.load(fh)

        for raw_dict in raw_dicts:
            ilib = InstalledLib(
                name=raw_dict['name'],
                version_dirs={Version(k): Path(v) for k, v in raw_dict['version_dirs'].items()}
            )

            res.libs[ilib.name] = ilib

        return res

    def lookup(self, lib_name: str) -> InstalledLib:
        return self.libs[lib_name]

    def register_install(self, lib: str, version: Version, container_dir: Path):
        ''' Adds an install to the registry in memory. '''
        if lib not in self.libs:
            self.libs[lib] = InstalledLib(
                name=lib,
                version_dirs={version: container_dir},
            )
        else:
            self.libs[lib].version_dirs[version] = container_dir

    def write_json(self, fh: TextIO):
        json.dump([
            {
                'name': l.name,
                'version_dirs': {str(k): str(v) for k, v in l.version_dirs.items()},
            }
            for l in self.libs.values()
        ], fh)


def load_installed_libs(config_dir: Path) -> InstalledLibRegistry:
    path = config_dir / INSTALLED_LIBS_FILE
    if not path.exists():
        return InstalledLibRegistry() # Empty registry

    with open(config_dir / INSTALLED_LIBS_FILE, 'r') as fh:
        return InstalledLibRegistry.read_json(fh)


def save_installed_libs(config_dir: Path, registry: InstalledLibRegistry) -> None:
    with open(config_dir / INSTALLED_LIBS_FILE, 'w') as fh:
        registry.write_json(fh)


def load_library_catalog(config_dir: Path) -> LibraryCatalog:
    res = LibraryCatalog()
    res.libs = {}
    with open(config_dir / CATALOG_FILE, 'rb') as fh:
        toml_dict = tomllib.load(fh)
        for key, subdict in toml_dict.items():
            if key.upper() == 'METADATA':
                continue  # This is a special key that contains top-level data
            
            version_objs = []
            for version_dict in subdict['versions']:
                version_objs.append(CatalogLibraryVersion(**version_dict))

            res.libs[key] = CatalogLibrary(
                name=key,
                full_name=subdict['full_name'],
                versions=version_objs,
                homepage=subdict["homepage"],
                license=subdict["license"],
            )

    return res
