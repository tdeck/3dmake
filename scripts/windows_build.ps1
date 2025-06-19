$ErrorActionPreference = "Stop"
pipenv sync # Often I just booted Windows and haven't updated this
pipenv run pyinstaller 3dm.spec -y
pushd dist
compress-archive -Force 3dmake\* 3dmake_windows.zip
popd
