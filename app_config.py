"""Shared runtime configuration for the ELO-NVH desktop application.

The JSON file is intentionally kept outside the executable so operators can
change paths and communication settings without rebuilding the application.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional


APP_NAME = "ELO-NVH"
PROJECT_ROOT = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    # Keep operational files alongside the portable onedir application.
    # The executable path is stable even though modules are loaded from
    # PyInstaller's internal directory.
    USER_ROOT = Path(sys.executable).resolve().parent
else:
    USER_ROOT = PROJECT_ROOT

DEFAULTS: Dict[str, Any] = {
    "ws_url": "ws://127.0.0.1:8081",
    "reconnect_interval": 3.0,
    "max_points": 400000,
    "fft_window_size": 1024,
    "sample_rate": 4800,
    "chart_refresh_interval": 50,
    "vibration_channels": ["x", "y", "z"],
    "y_axis_auto": True,
    "y_axis_min": -1.0,
    "y_axis_max": 1.0,
    "vibration_scale": 1.0,
    "backend_host": "0.0.0.0",
    "backend_port": 8081,
    "plc_ip": "192.168.3.124",
    "plc_port": 1025,
    "log_dir": str(USER_ROOT / "logs"),
    "data_save_dir": str(USER_ROOT / "logs" / "saved_data"),
    "new_data_save_dir": str(USER_ROOT / "data"),
    # Model files are application assets/data and are intentionally not user-editable.
    "model_dir": str(USER_ROOT / "logs" / "models"),
    "enable_new_save": True,
}


def canonical_model_dir() -> Path:
    """Return the only supported model directory for this installation."""
    return USER_ROOT / "logs" / "models"


def _migrate_bundled_models(target: Path) -> None:
    """Copy models from legacy/source locations without overwriting operators' files."""
    candidates = []
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", ""))
        candidates.extend([bundle_root / "logs" / "models", bundle_root / "websocket_backend" / "logs" / "models"])
    candidates.extend(
        [
            PROJECT_ROOT / "websocket_backend" / "logs" / "models",
            USER_ROOT / "websocket_backend" / "logs" / "models",
        ]
    )
    target.mkdir(parents=True, exist_ok=True)
    for source in candidates:
        if not source.is_dir() or source.resolve() == target.resolve():
            continue
        for item in source.glob("*.pth"):
            destination = target / item.name
            if not destination.exists():
                try:
                    shutil.copy2(item, destination)
                except OSError:
                    logging.getLogger(__name__).warning("迁移模型失败: %s", item, exc_info=True)


def config_path() -> Path:
    return USER_ROOT / "config.json"


def load() -> Dict[str, Any]:
    values = dict(DEFAULTS)
    path = config_path()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                values.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    except (OSError, ValueError) as exc:
        logging.getLogger(__name__).warning("读取配置失败 %s: %s", path, exc)
    # Ignore any historical/user-supplied model_dir value.  This keeps model
    # loading and training on the installation's logs/models directory.
    values["model_dir"] = str(canonical_model_dir())
    return values


def save(values: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in values.items() if k in DEFAULTS})
    merged["model_dir"] = str(canonical_model_dir())
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return merged


def ensure_directories(values: Optional[Dict[str, Any]] = None) -> None:
    values = values or load()
    values["model_dir"] = str(canonical_model_dir())
    for key in ("log_dir", "data_save_dir", "new_data_save_dir", "model_dir"):
        Path(str(values[key])).expanduser().mkdir(parents=True, exist_ok=True)
    _migrate_bundled_models(canonical_model_dir())


def configure_logging(values: Optional[Dict[str, Any]] = None) -> None:
    values = values or load()
    ensure_directories(values)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        Path(str(values["log_dir"])) / "yanpu.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(logging.StreamHandler())
