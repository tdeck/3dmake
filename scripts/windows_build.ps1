$ErrorActionPreference = "Stop"
pipenv install # Often I just booted Windows and haven't updated this

if ($args[0] -eq "--release") {
    Write-Output "Release build"
    pipenv run python scripts/release_check.py
}

pipenv run pyinstaller 3dm.spec -y
pushd dist
compress-archive -Force 3dmake\* 3dmake_windows.zip
popd
