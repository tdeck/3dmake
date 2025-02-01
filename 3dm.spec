# -*- mode: python ; coding: utf-8 -*-
# This file configures the PyInstaller build

import platform
from PyInstaller.utils.hooks import collect_submodules

deps_dir = {
    'Linux': 'deps/linux',
    'Windows': 'deps/windows',
}[platform.system()]


a = Analysis(
    ['3dm.py'],
    pathex=[],
    binaries=[],
    datas=[
        (f'./{deps_dir}', deps_dir),
        (f'./default_config', 'default_config'),
        (f'README.md', '.'),
    ],
    hiddenimports=[
        'prompt-toolkit', # For some reason pyinstaller doesn't pick this up in Windows
    ] + collect_submodules('vtkmodules'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='3dm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='3dmake',
)
