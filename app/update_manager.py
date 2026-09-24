"""Small, dependency-free updater used by the desktop application.

The updater downloads every Inno Setup split asset into one temporary directory,
then starts this executable in ``--apply-update`` mode.  A separate process is
required because Windows cannot replace a running executable.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from app.version import APP_VERSION, UPDATE_API_URL


@dataclass
class ReleaseInfo:
    version: str
    page_url: str
    notes: str
    assets: List[dict]


def _version(value: str):
    parts = re.findall(r"\d+", str(value))
    return tuple(int(item) for item in (parts + [0, 0, 0])[:3])


def is_newer(value: str) -> bool:
    return _version(value) > _version(APP_VERSION)


def fetch_latest_release(url: str = UPDATE_API_URL, timeout: float = 8.0) -> ReleaseInfo:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ELO-NVH-Updater", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = str(payload.get("tag_name") or payload.get("name") or "")
    version = tag.lstrip("vV")
    if not version:
        raise RuntimeError("远程版本信息缺少 tag_name")
    assets = []
    for item in payload.get("assets", []):
        name = str(item.get("name") or "")
        download_url = str(item.get("browser_download_url") or "")
        if name and download_url and name.lower().startswith("elo-nvh-setup-"):
            assets.append(
                {
                    "name": name,
                    "url": download_url,
                    "size": int(item.get("size") or 0),
                    "digest": str(item.get("digest") or ""),
                }
            )
    if not assets:
        raise RuntimeError("该版本没有找到 ELO-NVH 安装包附件")
    installer = [item for item in assets if item["name"].lower().endswith(".exe")]
    if not installer:
        raise RuntimeError("更新附件中没有安装程序 exe")
    return ReleaseInfo(
        version=version,
        page_url=str(payload.get("html_url") or ""),
        notes=str(payload.get("body") or "无更新说明"),
        assets=sorted(assets, key=lambda item: item["name"]),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_release(
    release: ReleaseInfo,
    progress: Optional[Callable[[int], None]] = None,
    status: Optional[Callable[[str], None]] = None,
) -> Path:
    target = Path(tempfile.mkdtemp(prefix=f"ELO-NVH-update-{release.version}-"))
    total = sum(max(0, int(item.get("size", 0))) for item in release.assets)
    completed = 0
    try:
        for item in release.assets:
            destination = target / item["name"]
            if status:
                status(f"正在下载 {item['name']}")
            request = urllib.request.Request(item["url"], headers={"User-Agent": "ELO-NVH-Updater"})
            with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                    completed += len(block)
                    if progress and total:
                        progress(min(99, int(completed * 100 / total)))
            expected = str(item.get("digest") or "")
            if expected.startswith("sha256:") and _sha256(destination) != expected.split(":", 1)[1].lower():
                raise RuntimeError(f"文件校验失败：{item['name']}")
        if progress:
            progress(100)
        installer = [path for path in target.glob("*.exe") if path.name.lower().startswith("elo-nvh-setup-")]
        if not installer:
            raise RuntimeError("下载完成但未找到安装程序")
        return installer[0]
    except Exception:
        # Keep no partial installer around after a failed download.
        for path in target.glob("*"):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            target.rmdir()
        except OSError:
            pass
        raise


def _wait_for_process(pid: int) -> None:
    if os.name != "nt":
        return
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))
    if handle:
        try:
            ctypes.windll.kernel32.WaitForSingleObject(handle, 30000)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)


def apply_update(installer: str, pid: int = 0, restart: bool = True) -> int:
    installer_path = Path(installer).resolve()
    if not installer_path.is_file():
        raise FileNotFoundError(installer_path)
    if pid:
        _wait_for_process(pid)
    subprocess.run(
        [str(installer_path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        cwd=str(installer_path.parent),
        check=True,
    )
    if restart:
        if getattr(sys, "frozen", False):
            command = [sys.executable]
            cwd = str(Path(sys.executable).resolve().parent)
        else:
            app_script = Path(__file__).resolve().parent / "desktop_app.py"
            command = [sys.executable, str(app_script)]
            cwd = str(app_script.parent.parent)
        subprocess.Popen(command, cwd=cwd)
    return 0


def launch_update(installer: Path) -> None:
    """Start the updater and return; the caller should close the Qt app."""
    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        command = [sys.executable, str(Path(__file__).resolve().parent / "desktop_app.py")]
    command.extend(["--apply-update", "--installer", str(installer), "--pid", str(os.getpid())])
    subprocess.Popen(command, cwd=str(Path(sys.executable).resolve().parent))
