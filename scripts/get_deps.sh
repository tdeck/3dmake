#! /bin/bash
set -e

DEPDIR="$(readlink -f $(dirname "$0")/../deps)"

mkdir -p "$DEPDIR/windows"
mkdir -p "$DEPDIR/linux"

#
# Linux
#
#curl 'https://files.openscad.org/OpenSCAD-2021.01-x86_64.AppImage' > "$DEPDIR/linux/OpenSCAD.AppImage"
#curl -L 'https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.8.1/PrusaSlicer-2.8.1+linux-x64-older-distros-GTK3-202409181354.AppImage' > "$DEPDIR/linux/PrusaSlicer.AppImage"
#
#chmod +x "$DEPDIR/linux/OpenSCAD.AppImage"
#chmod +x "$DEPDIR/linux/PrusaSlicer.AppImage"
 
#
# Windows
# 
TMPDIR="$(mktemp -d)"
echo "tmp dir $TMPDIR"
pushd "$TMPDIR"
curl 'https://files.openscad.org/OpenSCAD-2021.01-x86-64.zip' > scad.zip
curl -L 'https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.8.1/PrusaSlicer-2.8.1+win64-202409181359.zip' > slicer.zip

mkdir scad
(
    cd scad
    unzip ../scad.zip
    mv "$(ls -1 | head -n 1)" "$DEPDIR/windows/openscad"
)

mkdir slicer
(
    cd slicer
    unzip ../slicer.zip

    mv "$(ls -1 | head -n 1)" "$DEPDIR/windows/prusaslicer"
)

popd
rm -rf "$TMPDIR"
