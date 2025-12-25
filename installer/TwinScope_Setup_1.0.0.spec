# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['F:\\TwinScope_v1.0\\installer\\installer_source.py'],
    pathex=[],
    binaries=[],
    datas=[('F:\\TwinScope_v1.0\\installer\\payload.zip', '.'), ('F:\\TwinScope_v1.0\\installer\\setup_icon.ico', '.')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='TwinScope_Setup_1.0.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['F:\\TwinScope_v1.0\\installer\\setup_icon.ico'],
)
