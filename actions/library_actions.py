from packaging.version import Version
from typing import TextIO, Optional
from pathlib import Path
import tempfile
import zipfile
import shutil

import requests

from .framework import Context, isolated_action
from utils.libs import load_installed_libs, save_installed_libs, load_library_catalog

LIBRARY_INSTALL_DIR = 'libraries'

def make_dir_for_lib(config_dir: Path, lib_name: str, version: Version) -> Path:
    ''' Chooses and creates (mkdir -p) a path for the given lib version. '''
    path = config_dir / LIBRARY_INSTALL_DIR / f"{lib_name}__{version}"
    path.mkdir(parents=True)
    return path.absolute()

def extract_zip_to_folder(zipfh: TextIO, subdir: Optional[str], outdir: Path) -> None:
    subpath_obj = Path(subdir or '.')
    
    with zipfile.ZipFile(zipfh, 'r') as unzipper:
        for name in unzipper.namelist():
            file_info = unzipper.getinfo(name)

            # Skip handling directories directly
            if file_info.is_dir():
                continue

            entry_path = Path(name)

            if not entry_path.is_relative_to(subpath_obj):
                # Note: is_relative_to is a very poorly named function, but basically it asks if
                # p is a child of q
                continue

            target_path = outdir / entry_path.relative_to(subpath_obj)

            # We can't simply use extract here, because it will append all the directories
            # in the zip entry, so we copy it using zipfile's open method
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with unzipper.open(name) as ifh, open(target_path, 'wb') as ofh:
                shutil.copyfileobj(ifh, ofh)

@isolated_action(needs_options=True)
def list_libraries(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Lists available OpenSCAD libraries. '''
    catalog = load_library_catalog(ctx.config_dir)
    registry = load_installed_libs(ctx.config_dir)

    stdout.write("Available libraries:\n\n")

    for library in catalog.libs.values():
        installed = registry.libs.get(library.name)
        if installed:
            stdout.write(f"Library: {library.name} (version {installed.latest_version()} installed)\n")
        else:
            stdout.write(f"Library: {library.name}\n")

        stdout.write(f"Full name: {library.full_name}\n")
        stdout.write(f"Homepage: {library.homepage}\n")
        stdout.write(f"License: {library.license}\n")
        stdout.write(f"Latest version: {library.latest_version().version}\n")
        stdout.write("\n")



@isolated_action(needs_options=True)
def install_libraries(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Ensures that all libraries needed by the current project are installed. '''

    # Determine which libraries are needed
    lib_registry = load_installed_libs(ctx.config_dir)
    needed_libs = set(ctx.options.libraries) - set(lib_registry.libs.keys())
    if not needed_libs:
        stdout.write("All needed libraries are installed.\n")

    # Load the library catalog
    catalog = load_library_catalog(ctx.config_dir)

    for lib_name in needed_libs:
        catalog_entry = catalog.libs.get(lib_name)

        if not catalog_entry:
            raise RuntimeError(f"No library named '{lib_name}' exists in the library catalog.")
    
        latest_catalog_version = catalog_entry.latest_version()

        stdout.write(f"Downloading {lib_name} version {latest_catalog_version.version}...\n")

        with tempfile.TemporaryFile(suffix=".zip") as zipfh:
            response = requests.get(latest_catalog_version.archive, stream=True)
            response.raise_for_status()

            for chunk in response.iter_content(chunk_size=8192): # TODO tune chunk size
                zipfh.write(chunk)

            stdout.write(f"Extracting library...\n")
            zipfh.seek(0)

            # container_dir gets added to the PATH, but the lib contents go in outdir
            container_dir = make_dir_for_lib(ctx.config_dir, lib_name, latest_catalog_version.version)
            outdir = container_dir / lib_name

            extract_zip_to_folder(zipfh, latest_catalog_version.subdir, outdir)

            lib_registry.register_install(lib_name, latest_catalog_version.version, container_dir)

    save_installed_libs(ctx.config_dir, lib_registry)
