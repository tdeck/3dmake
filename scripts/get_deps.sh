#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPDIR="$(cd "$SCRIPT_DIR/../deps" && pwd)"

OPENSCAD_VERSION="2021.01"
PRUSASLICER_MACOS_VERSION="2.9.4"

OPENSCAD_LINUX_URL="https://files.openscad.org/OpenSCAD-${OPENSCAD_VERSION}-x86_64.AppImage"
OPENSCAD_WINDOWS_URL="https://files.openscad.org/OpenSCAD-${OPENSCAD_VERSION}-x86-64.zip"
OPENSCAD_MACOS_URL="https://files.openscad.org/OpenSCAD-${OPENSCAD_VERSION}.dmg"

PRUSASLICER_LINUX_URL="https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.8.1/PrusaSlicer-2.8.1%2Blinux-x64-older-distros-GTK3-202409181354.AppImage"
PRUSASLICER_WINDOWS_URL="https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.8.1/PrusaSlicer-2.8.1%2Bwin64-202409181359.zip"
PRUSASLICER_MACOS_URL="https://github.com/prusa3d/PrusaSlicer/releases/download/version_${PRUSASLICER_MACOS_VERSION}/PrusaSlicer-${PRUSASLICER_MACOS_VERSION}.dmg"
OPENSCAD_MACOS_APP="${OPENSCAD_MACOS_APP:-/Applications/OpenSCAD.app}"

usage() {
    echo "Usage: scripts/get_deps.sh [linux|windows|macos|all]"
    echo "Without an argument, downloads Windows dependencies to preserve the old default."
}

new_tmpdir() {
    # GNU mktemp accepts `mktemp -d`, but some BSD/macOS versions expect a template.
    mktemp -d 2>/dev/null || mktemp -d -t 3dmake_deps
}

download_linux() {
    mkdir -p "$DEPDIR/linux"
    curl -L "$OPENSCAD_LINUX_URL" -o "$DEPDIR/linux/OpenSCAD.AppImage"
    curl -L "$PRUSASLICER_LINUX_URL" -o "$DEPDIR/linux/PrusaSlicer.AppImage"
    chmod +x "$DEPDIR/linux/OpenSCAD.AppImage"
    chmod +x "$DEPDIR/linux/PrusaSlicer.AppImage"
}

download_windows() {
    mkdir -p "$DEPDIR/windows"

    local tmpdir
    tmpdir="$(new_tmpdir)"
    echo "tmp dir $tmpdir"
    pushd "$tmpdir" >/dev/null

    curl -L "$OPENSCAD_WINDOWS_URL" -o scad.zip
    curl -L "$PRUSASLICER_WINDOWS_URL" -o slicer.zip

    mkdir scad
    (
        cd scad
        unzip -q ../scad.zip
        rm -rf "$DEPDIR/windows/openscad"
        mv "$(ls -1 | head -n 1)" "$DEPDIR/windows/openscad"
    )

    mkdir slicer
    (
        cd slicer
        unzip -q ../slicer.zip
        rm -rf "$DEPDIR/windows/prusaslicer"
        mv "$(ls -1 | head -n 1)" "$DEPDIR/windows/prusaslicer"
    )

    popd >/dev/null
    rm -rf "$tmpdir"
}

copy_app_from_dmg() {
    local dmg_path="$1"
    local app_name="$2"
    local dest_path="$3"
    local mount_path="$4"

    mkdir -p "$mount_path"
    hdiutil attach "$dmg_path" -mountpoint "$mount_path" -nobrowse -quiet
    rm -rf "$dest_path"
    local mounted_app
    # PrusaSlicer's DMG nests the app under "Original Prusa Drivers" instead of the volume root.
    mounted_app="$(find "$mount_path" -maxdepth 3 -name "$app_name" -type d -print -quit)"
    if [[ -z "$mounted_app" ]]; then
        echo "Could not find $app_name in $dmg_path" >&2
        hdiutil detach "$mount_path" -quiet
        return 1
    fi
    if ! cp -R "$mounted_app" "$dest_path"; then
        hdiutil detach "$mount_path" -quiet
        return 1
    fi
    hdiutil detach "$mount_path" -quiet

    if command -v xattr >/dev/null; then
        # Downloaded DMGs can add quarantine metadata that makes Gatekeeper warn or block helper apps.
        xattr -dr com.apple.quarantine "$dest_path" 2>/dev/null || true
    fi
}

download_macos() {
    if [[ "$(uname -s)" != "Darwin" ]]; then
        echo "macOS dependencies must be extracted on macOS because they are distributed as DMG files." >&2
        exit 1
    fi

    mkdir -p "$DEPDIR/macos"

    local tmpdir
    tmpdir="$(new_tmpdir)"
    echo "tmp dir $tmpdir"

    if [[ -d "$OPENSCAD_MACOS_APP" ]]; then
        rm -rf "$DEPDIR/macos/OpenSCAD.app"
        cp -R "$OPENSCAD_MACOS_APP" "$DEPDIR/macos/OpenSCAD.app"
    else
        curl -L "$OPENSCAD_MACOS_URL" -o "$tmpdir/openscad.dmg"
        copy_app_from_dmg "$tmpdir/openscad.dmg" "OpenSCAD.app" "$DEPDIR/macos/OpenSCAD.app" "$tmpdir/openscad_mount"
    fi

    curl -L "$PRUSASLICER_MACOS_URL" -o "$tmpdir/prusaslicer.dmg"

    copy_app_from_dmg "$tmpdir/prusaslicer.dmg" "PrusaSlicer.app" "$DEPDIR/macos/PrusaSlicer.app" "$tmpdir/prusaslicer_mount"

    rm -rf "$tmpdir"
}

target="${1:-windows}"
case "$target" in
    linux)
        download_linux
        ;;
    windows)
        download_windows
        ;;
    macos|darwin)
        download_macos
        ;;
    all)
        download_linux
        download_windows
        download_macos
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 1
        ;;
esac
