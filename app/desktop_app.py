"""Single-process desktop launcher for the packaged application."""
import os
import sys
import subprocess
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
FRONTEND = ROOT / "qianduan"
BACKEND = ROOT / "websocket_backend"
for path in (ROOT, FRONTEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app_config import configure_logging


def _install_module_aliases(package, names):
    """Keep legacy absolute imports working inside the frozen package."""
    for name in names:
        module = importlib.import_module(f"{package}.{name}")
        sys.modules[name] = module


def main():
    configure_logging()
    if "--backend-only" in sys.argv:
        sys.path.insert(0, str(BACKEND))
        _install_module_aliases("websocket_backend", [
            # The legacy backend uses absolute imports. Load aliases in their
            # dependency order so each module observes the backend config.
            "config", "plc_comm", "plc_manager", "model", "model_inference",
            "websocket_server", "shared_data_acquisition", "station_worker",
        ])
        from websocket_backend.main import main as backend_main
        backend_main()
        return 0

    backend_process = None
    if "--no-backend" not in sys.argv and "--mock" not in sys.argv:
        backend_process = subprocess.Popen([sys.executable, "--backend-only"], cwd=str(APP_ROOT))

    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import QApplication
    _install_module_aliases("qianduan", ["config", "fft_utils"])
    sys.modules["ui"] = importlib.import_module("qianduan.ui")
    from qianduan.ui.main_window import MainWindow
    from qianduan.config import WS_URL, RECONNECT_INTERVAL

    app = QApplication(sys.argv)
    app.setApplicationName("Yanpu 振动质检系统")
    app.setOrganizationName("Yanpu")
    app.setFont(QFont("Microsoft YaHei", 10))
    window = MainWindow()
    if "--csv" in sys.argv:
        idx = sys.argv.index("--csv")
        csv_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--") else "data/ch0.csv"
        from qianduan.csv_data_source import CsvDataSource
        source = CsvDataSource(csv_path=csv_path, interval_ms=50, batch_size=100)
    elif "--mock" in sys.argv:
        from qianduan.mock_data import MockDataSource
        source = MockDataSource(interval_ms=50, batch_size=10)
    else:
        from qianduan.websocket_client import WebSocketClient
        source = WebSocketClient(url=WS_URL, reconnect_interval=RECONNECT_INTERVAL)
    window.connect_data_source(source)
    source.start()
    window.show()
    try:
        return app.exec_()
    finally:
        if backend_process and backend_process.poll() is None:
            backend_process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
