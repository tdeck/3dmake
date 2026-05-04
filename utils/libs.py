import json
from typing import TextIO, Optional
from pathlib import Path
from dataclasses import dataclass
from packaging.version import Version
import tomllib

from coretypes import CommandOptions
from utils.bundle_paths import BUNDLED_SCAD_LIB_PATH

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


def resolve_lib_include_dirs(config_dir: Path, options: CommandOptions) -> list[Path]:
    lib_registry = load_installed_libs(config_dir)
    needed_libs = set(options.libraries) - set(lib_registry.libs.keys())

    if needed_libs:
        raise RuntimeError(
            f"Some needed libraries are not installed: {' '.join(needed_libs)}"
            "\nRun 3dm install-libraries."
        )

    lib_include_dirs = [
        lib_registry.lookup(lib_name).latest_version_dir()
        for lib_name in options.libraries
    ]

    for local_lib in options.local_libraries:
        ll_path = Path(local_lib)
        if not ll_path.is_absolute():
            ll_path = ll_path.absolute()
            # TODO if these paths are relative, it'll work now because of how
            # 3dm is always run from a project root, but it may not work in the
            # future
        lib_include_dirs.append(ll_path)

    lib_include_dirs.append(BUNDLED_SCAD_LIB_PATH)
    return lib_include_dirs


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
