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
# IMPORTANT: for the windows build the 3dm.exe is in the top level dir. This is required for self-install to work.
