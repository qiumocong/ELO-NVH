"""PyInstaller runtime hook: initialize NI before the PyQt5 runtime hook."""
import sys


if not any(flag in sys.argv for flag in ("--mock", "--csv", "--no-backend")):
    from app.ni_runtime import prepare_nidaqmx_runtime

    prepare_nidaqmx_runtime()
