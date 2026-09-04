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
        ("../qianduan/yanpu_logo.png", "qianduan"),
    ] + copy_metadata("nidaqmx"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["app/ni_runtime_hook.py"],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    name="ELO-NVH",
    icon="../qianduan/elo_nvh.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # NI-DAQmx is loaded dynamically from the system installation. Avoid UPX
    # transformations in the launcher and native dependency tree.
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="ELO-NVH",
)
