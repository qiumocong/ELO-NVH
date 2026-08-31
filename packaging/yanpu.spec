# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

hiddenimports = (
    collect_submodules("qianduan")
    + collect_submodules("websocket_backend")
    + ["nidaqmx", "websockets"]
)

a = Analysis(
    ["../app/desktop_app.py"],
    pathex=[".."],
    binaries=[],
    datas=[
        ("../websocket_backend/logs/models", "websocket_backend/logs/models"),
    ] + copy_metadata("nidaqmx"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    name="Yanpu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=True,
    name="Yanpu",
)
