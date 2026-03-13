#! /bin/bash
set -e

# Ensure we are in the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

pipenv install --dev

if [[ "$1" == "--release" ]]; then
    echo "Release build"
    pipenv run python scripts/release_check.py
fi

pipenv run pyinstaller -y 3dm.spec
cd dist
tar -czvf 3dmake_linux.tar.gz 3dmake
