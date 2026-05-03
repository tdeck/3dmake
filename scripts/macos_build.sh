#! /bin/bash
set -e
pipenv sync --dev

if [[ "$1" == "--release" ]]; then
    echo "Release build"
    pipenv run python scripts/release_check.py
fi

pipenv run pyinstaller -y 3dm.spec
cd dist
tar -czvf 3dmake_macos.tar.gz 3dmake
