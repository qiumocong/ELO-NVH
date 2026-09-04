"""NI-DAQmx startup workarounds for the PyInstaller desktop build."""
from __future__ import annotations

import logging
import os
import sys
import ctypes
from pathlib import Path
from typing import List


_dll_directories: List[object] = []
_prepared = False


def prepare_nidaqmx_runtime() -> None:
    """Prepare NI-DAQmx before the first ``nidaqmx.Task`` is created.

    NI-DAQmx is installed system-wide and must never be resolved from the
    PyInstaller bundle. Loading the library before the worker thread starts
    also avoids a frozen-process ctypes call seeing an uninitialized handle.
    """
    global _prepared
    if _prepared:
        return
    _prepared = True

    if not (getattr(sys, "frozen", False) and sys.platform.startswith("win")):
        return

    logger = logging.getLogger(__name__)
    system32 = Path(os.environ.get("SystemRoot", r"C:\\Windows")) / "System32"
    if hasattr(os, "add_dll_directory") and system32.is_dir():
        try:
            # Keep the handle alive for the lifetime of the process.
            _dll_directories.append(os.add_dll_directory(str(system32)))
        except OSError as exc:
            logger.warning("无法添加 NI-DAQmx DLL 搜索路径 %s: %s", system32, exc)

    try:
        # nicaiu is the stable ANSI entry point supported by all current
        # NI-DAQmx Windows installations. Set this before importing nidaqmx.
        os.environ.setdefault("NIDAQMX_C_LIBRARY", "nicaiu")
        from nidaqmx import _lib

        dll_path = system32 / "nicaiu.dll"
        if not dll_path.is_file():
            raise FileNotFoundError("未找到 NI-DAQmx 驱动: %s" % dll_path)
        # Bind both calling-convention handles to the same absolute DLL path.
        # This avoids LoadLibrary resolving a stale copy from PATH in a frozen
        # process.
        _lib.lib_importer._windll = _lib.DaqFunctionImporter(
            ctypes.WinDLL(str(dll_path))
        )
        _lib.lib_importer._cdll = _lib.DaqFunctionImporter(
            ctypes.CDLL(str(dll_path))
        )
        _lib.lib_importer._encoding = _lib.get_encoding_from_locale()
        logger.info("NI-DAQmx 已使用系统驱动初始化: %s", dll_path)
    except Exception:
        logger.exception("NI-DAQmx 运行时初始化失败")
        raise
