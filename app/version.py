"""Application identity and update endpoint."""
import re
from pathlib import Path

APP_NAME = "ELO-NVH"
# PyInstaller ships this same file at the root of its internal data directory.
APP_VERSION = (Path(__file__).resolve().parents[1] / ".app_version").read_text(encoding="utf-8-sig").strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION):
    raise ValueError("Invalid .app_version: expected MAJOR.MINOR.PATCH")

# The endpoint returns the latest GitHub Release and its installer assets.
UPDATE_API_URL = "https://api.github.com/repos/qiumocong/ELO-NVH/releases/latest"
