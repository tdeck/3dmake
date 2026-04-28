$ErrorActionPreference = "Stop"
pipenv sync --dev

if ($args[0] -eq "--release") {
    Write-Output "Release build"
    pipenv run python scripts/release_check.py
}

pipenv run pyinstaller 3dm.spec -y
Add-Type -Assembly System.IO.Compression.FileSystem
$distDir = Resolve-Path 'dist'
Remove-Item -Force "$distDir\3dmake_windows.zip" -ErrorAction SilentlyContinue
echo 'Creating ZIP file...'
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    "$distDir\3dmake",
    "$distDir\3dmake_windows.zip",
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false # includeBaseDirectory
)
# IMPORTANT: for the windows build the 3dm.exe is in the top level dir. This is required for self-install to work.
