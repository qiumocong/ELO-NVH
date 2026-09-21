# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata

# Keep the production build limited to modules used by the desktop workflow.
# Training utilities and optional vision/audio packages are intentionally kept
# in the development environment and are not needed for online inference.
hiddenimports = [
    "qianduan.config",
    "qianduan.fft_utils",
    "qianduan.mock_data",
    "qianduan.websocket_client",
    "qianduan.ui",
    "qianduan.ui.header_widget",
    "qianduan.ui.labeler_panel",
    "qianduan.ui.labeler_window",
    "qianduan.ui.main_window",
    "qianduan.ui.result_panel",
    "qianduan.ui.scale_dialog",
    "qianduan.ui.settings_dialog",
    "qianduan.ui.spectrum_chart",
    "qianduan.ui.status_bar",
    "qianduan.ui.system_settings_dialog",
    "qianduan.ui.time_chart",
    "qianduan.ui.update_dialog",
    "websocket_backend.config",
    "websocket_backend.main",
    "websocket_backend.model",
    "websocket_backend.model_inference",
    "websocket_backend.plc_comm",
    "websocket_backend.plc_manager",
    "websocket_backend.shared_data_acquisition",
    "websocket_backend.station_worker",
    "websocket_backend.websocket_server",
    "nidaqmx",
    "pymcprotocol",
    "torch",
    "websockets",
]

a = Analysis(
    ["../app/desktop_app.py"],
    pathex=[".."],
    binaries=[],
    datas=[
        ("../qianduan/yanpu_logo.png", "qianduan"),
    ] + copy_metadata("nidaqmx"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["app/ni_runtime_hook.py"],
    excludes=[
        "tkinter",
        "sklearn",
        "torchvision",
        "torchaudio",
        "websocket_backend.model_new",
        "websocket_backend.train_from_saved",
        "websocket_backend.train_from_saved_new",
    ],
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
