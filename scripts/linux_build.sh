#! /bin/bash
set -e
pipenv sync --dev

if [[ "$1" == "--release" ]]; then
    echo "Release build"
    pipenv run python scripts/release_check.py
fi

pipenv run pyinstaller -y 3dm.spec
cd dist
tar -czvf 3dmake_linux.tar.gz 3dmake
# IMPORTANT: the software must be inside a 3dmake folder in the archive, or auto-update will fail
