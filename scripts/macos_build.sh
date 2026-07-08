#! /bin/bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
    echo "Usage: scripts/macos_build.sh [--release]"
    exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "macOS builds must be created on macOS."
    exit 1
fi

if [[ ! -x "deps/macos/OpenSCAD.app/Contents/MacOS/OpenSCAD" || ! -x "deps/macos/PrusaSlicer.app/Contents/MacOS/PrusaSlicer" ]]; then
    echo "Missing bundled macOS dependencies. Run scripts/get_deps.sh macos first."
    exit 1
fi

uv sync -q

if [[ "${1:-}" == "--release" ]]; then
    echo "Release build"
    uv run python scripts/release_check.py
fi

uv run pyinstaller --clean -y 3dm.spec
rm -rf dist/3dmake/_internal/deps/macos
mkdir -p dist/3dmake/_internal/deps
mkdir -p dist/3dmake/_internal/deps/macos
cp -R deps/macos/OpenSCAD.app deps/macos/PrusaSlicer.app dist/3dmake/_internal/deps/macos
cd dist
rm -f 3dmake_macos.tar.gz
tar -czf 3dmake_macos.tar.gz 3dmake
# IMPORTANT: the software must be inside a 3dmake folder in the archive, or auto-update will fail
