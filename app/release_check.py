"""Validate the frozen release without connecting to NI hardware or the PLC."""
import importlib
import math
import os


def run_self_test():
    from app.desktop_app import _install_module_aliases
    from app.version import APP_VERSION
    from app_config import canonical_model_dir

    print("[SELF-TEST] ELO-NVH {}".format(APP_VERSION), flush=True)
    _install_module_aliases("websocket_backend", ["config", "model", "model_inference"])
    for name in (
        "nidaqmx", "pymcprotocol", "websockets",
        "websocket_backend.shared_data_acquisition",
        "websocket_backend.websocket_server",
        "websocket_backend.scaled_data_writer",
    ):
        importlib.import_module(name)
    print("[SELF-TEST] Backend dependencies imported (no device connections)", flush=True)

    import numpy as np
    import torch
    from websocket_backend.model_inference import get_model_for_spec, preprocess, predict

    model_dir = canonical_model_dir()
    model_paths = sorted(model_dir.glob("*.pth"))
    if not (model_dir / "default.pth").is_file():
        raise RuntimeError("Missing default.pth: {}".format(model_dir))
    for path in model_paths:
        model = get_model_for_spec(path.stem)
        for side in ("left", "right"):
            tensor = preprocess(np.zeros((3, 2400), dtype=np.float32), side)
            label, score = predict(model, tensor)
            if label not in (0, 1) or not math.isfinite(score) or not 0 <= score <= 1:
                raise RuntimeError("Invalid model output: {} / {}".format(path.name, side))
        print("[SELF-TEST] Model {}: CPU inference passed".format(path.name), flush=True)
    print("[SELF-TEST] PyTorch {} / CUDA {}".format(torch.__version__, torch.version.cuda), flush=True)

    # Run the real widgets and data handlers using Qt's headless platform.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtCore import QEventLoop, QTimer
    from PyQt5.QtWidgets import QApplication

    _install_module_aliases("qianduan", ["config", "fft_utils"])
    import sys
    sys.modules["ui"] = importlib.import_module("qianduan.ui")
    from qianduan.ui.main_window import MainWindow
    from qianduan.ui.system_settings_dialog import SystemSettingsDialog
    from qianduan.mock_data import MockDataSource

    application = QApplication.instance() or QApplication(["ELO-NVH", "--self-test"])
    window = MainWindow()
    settings = SystemSettingsDialog(window)
    if window._logo_label.pixmap() is None or window._logo_label.pixmap().isNull():
        raise RuntimeError("Missing application logo")
    source = MockDataSource(interval_ms=20, batch_size=100, auto_start=True)
    window.connect_data_source(source)
    source.start()
    loop = QEventLoop()
    QTimer.singleShot(1500, loop.quit)
    loop.exec_()
    source.stop()
    if not all(window._side_has_data.values()) or window._diag_rx_count < 4:
        raise RuntimeError("Both stations must receive mock data")
    for charts in window._charts.values():
        for chart in charts.values():
            if len(chart._values) < 64:
                raise RuntimeError("Missing chart samples")
    print("[SELF-TEST] GUI, settings, logo, both stations and chart updates passed", flush=True)
    settings.close()
    window.close()
    application.processEvents()
    print("[SELF-TEST] PASS (NI hardware and PLC require separate validation)", flush=True)
    return 0
