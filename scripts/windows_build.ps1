$ErrorActionPreference = "Stop"
pipenv sync --dev

if ($args[0] -eq "--release") {
    Write-Output "Release build"
    pipenv run python scripts/release_check.py
}

pipenv run pyinstaller 3dm.spec -y
pushd dist
compress-archive -Force 3dmake\* 3dmake_windows.zip
popd
# IMPORTANT: the software must be inside a 3dmake folder in the archive, or auto-update will fail
