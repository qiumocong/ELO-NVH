"""Small, dependency-free updater used by the desktop application.

The updater downloads every Inno Setup split asset into one temporary directory,
then starts this executable in ``--apply-update`` mode.  A separate process is
required because Windows cannot replace a running executable.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from app.version import APP_VERSION, UPDATE_API_URL


_LOGGER = logging.getLogger(__name__)


def _update_log_path() -> Path:
    """Return a writable log path even when the update process runs alone."""
    if getattr(sys, "frozen", False):
        candidates = [Path(sys.executable).resolve().parent / "logs" / "update.log"]
    else:
        candidates = [Path(__file__).resolve().parents[1] / "logs" / "update.log"]
    candidates.append(Path(tempfile.gettempdir()) / "ELO-NVH-update.log")
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("a", encoding="utf-8"):
                pass
            return candidate
        except OSError:
            continue
    return candidates[-1]


def _update_log(message: str, *, error: Optional[BaseException] = None) -> None:
    """Write update diagnostics before the normal application logger starts."""
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    if error is not None:
        line += f" ({type(error).__name__}: {error})"
    try:
        path = _update_log_path()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
    _LOGGER.info(line)


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
    progress_detail: Optional[Callable[[int, int], None]] = None,
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
                    if progress_detail:
                        progress_detail(completed, total)
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
    frozen = bool(getattr(sys, "frozen", False))
    app_executable = Path(sys.executable).resolve()
    app_dir = app_executable.parent
    _update_log(
        f"开始应用更新: installer={installer_path}; pid={pid}; "
        f"current_executable={app_executable}; frozen={frozen}"
    )
    if pid:
        _update_log(f"等待旧进程退出: pid={pid}")
        _wait_for_process(pid)
        _update_log(f"旧进程等待结束: pid={pid}")

    # Installing into the directory from which the update was launched avoids
    # updating the default install directory while restarting an older portable
    # copy from dist\ELO-NVH.  /DIR is supported by Inno Setup and is harmless
    # for the normal per-user installation path.
    command = [
        str(installer_path),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
    ]
    if frozen:
        command.append(f"/DIR={app_dir}")
    _update_log(f"启动安装程序: {' '.join(command)}")
    try:
        result = subprocess.run(command, cwd=str(installer_path.parent), check=False)
    except Exception as exc:
        _update_log("启动安装程序失败", error=exc)
        raise
    _update_log(f"安装程序已退出: returncode={result.returncode}")
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command)

    if restart:
        if frozen:
            restart_executable = app_dir / app_executable.name
            command = [str(restart_executable)]
            cwd = str(app_dir)
        else:
            app_script = Path(__file__).resolve().parent / "desktop_app.py"
            command = [sys.executable, str(app_script)]
            cwd = str(app_script.parent.parent)
        _update_log(f"重启程序: {' '.join(command)}; cwd={cwd}")
        try:
            subprocess.Popen(command, cwd=cwd)
        except Exception as exc:
            _update_log("重启程序失败", error=exc)
            raise
    return 0


def launch_update(installer: Path) -> None:
    """Start an updater that does not keep the application exe locked.

    A frozen PyInstaller executable cannot safely update itself while it is
    still the process running the installer.  On Windows we therefore use the
    built-in PowerShell host as a tiny detached helper.  The old self-updater
    remains the fallback for source runs and unusual systems without
    ``powershell.exe``.
    """
    installer = Path(installer).resolve()
    app_executable = Path(sys.executable).resolve()
    cwd = app_executable.parent
    pid = os.getpid()

    if getattr(sys, "frozen", False) and os.name == "nt":
        def ps_quote(value: object) -> str:
            return "'" + str(value).replace("'", "''") + "'"

        log_path = cwd / "logs" / "update.log"
        # The script is deliberately self-contained: it can continue after
        # the Qt process exits and does not import or lock ELO-NVH.exe.
        script = f"""
$ErrorActionPreference = 'Stop'
$oldPid = {pid}
$installerPath = {ps_quote(installer)}
$appPath = {ps_quote(app_executable)}
$appDir = {ps_quote(cwd)}
$logPath = {ps_quote(log_path)}
$fallbackLogPath = Join-Path $env:TEMP 'ELO-NVH-update.log'
function Write-UpdateLog([string]$Message) {{
    $line = (Get-Date -Format 's') + ' ' + $Message
    foreach ($candidate in @($logPath, $fallbackLogPath)) {{
        try {{
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $candidate) | Out-Null
            Add-Content -LiteralPath $candidate -Value $line -Encoding UTF8
            return
        }} catch {{ }}
    }}
}}
try {{
    Write-UpdateLog "PowerShell 更新辅助进程启动: pid=$oldPid installer=$installerPath"
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {{
        Start-Sleep -Milliseconds 250
    }}
    if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {{
        throw "主程序在 60 秒内未退出 (pid=$oldPid)"
    }}
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/DIR=' + $appDir))
    $installerProcess = Start-Process -FilePath $installerPath -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $installerPath) -Wait -PassThru
    Write-UpdateLog "安装程序退出: code=$($installerProcess.ExitCode)"
    if ($installerProcess.ExitCode -ne 0) {{
        throw "安装程序返回错误码 $($installerProcess.ExitCode)"
    }}
    Start-Process -FilePath $appPath -WorkingDirectory $appDir
    Write-UpdateLog "已重启程序: $appPath"
}} catch {{
    Write-UpdateLog ("更新失败: " + $_.Exception.Message)
    try {{
        Start-Process -FilePath $appPath -WorkingDirectory $appDir
        Write-UpdateLog "更新失败后已恢复启动旧版本"
    }} catch {{ }}
    exit 1
}}
"""
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell:
            command = [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ]
            _update_log(f"启动独立更新辅助进程: installer={installer}; app={app_executable}; pid={pid}")
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(command, cwd=str(cwd), creationflags=creationflags)
            return
        _update_log("未找到 powershell.exe，回退到兼容更新进程")

    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        command = [sys.executable, str(Path(__file__).resolve().parent / "desktop_app.py")]
    command.extend(["--apply-update", "--installer", str(installer), "--pid", str(pid)])
    _update_log(f"启动兼容更新进程: {' '.join(command)}; cwd={cwd}")
    subprocess.Popen(command, cwd=str(cwd))
