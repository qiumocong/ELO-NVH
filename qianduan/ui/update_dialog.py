"""Software update dialog and background network workers."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from app.update_manager import ReleaseInfo, download_release, fetch_latest_release, is_newer, launch_update
from app.version import APP_NAME, APP_VERSION


class _CheckWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.succeeded.emit(fetch_latest_release())
        except Exception as exc:
            logging.getLogger(__name__).warning("检查更新失败: %s", exc)
            self.failed.emit(str(exc))


class _DownloadWorker(QThread):
    progress = pyqtSignal(int)
    progress_detail = pyqtSignal(int, int)
    status = pyqtSignal(str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self.release = release

    def run(self):
        try:
            installer = download_release(
                self.release,
                self.progress.emit,
                self.status.emit,
                self.progress_detail.emit,
            )
            self.succeeded.emit(installer)
        except Exception as exc:
            logging.getLogger(__name__).exception("下载更新失败")
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("软件更新")
        self.setMinimumWidth(560)
        self._release = None
        self._worker = None
        self._last_download_status = ""
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        self._current = QLabel(f"当前版本：{APP_VERSION}")
        self._latest = QLabel("尚未检查更新")
        self._latest.setWordWrap(True)
        self._notes = QLabel("")
        self._notes.setWordWrap(True)
        self._status = QLabel("点击“检查更新”获取最新版本信息。")
        self._status.setWordWrap(True)
        self._phase = QLabel("阶段：未开始")
        self._phase.setStyleSheet("font-weight: 600; color: #36566f;")
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFormat("%p%")
        self._progress.setVisible(False)
        self._progress_detail = QLabel("")
        self._progress_detail.setStyleSheet("color: #687782;")
        self._progress_detail.setVisible(False)
        self._check = QPushButton("检查更新")
        self._install = QPushButton("下载并安装")
        self._install.setEnabled(False)
        self._check.clicked.connect(self.check)
        self._install.clicked.connect(self.download)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(self._current)
        layout.addWidget(self._latest)
        layout.addWidget(self._notes)
        layout.addWidget(self._status)
        layout.addWidget(self._phase)
        layout.addWidget(self._progress)
        layout.addWidget(self._progress_detail)
        layout.addWidget(self._check)
        layout.addWidget(self._install)
        layout.addWidget(buttons)

    def check(self):
        self._check.setEnabled(False)
        self._install.setEnabled(False)
        self._phase.setText("阶段 1/3：检查更新")
        self._show_progress(indeterminate=True, detail="正在连接 GitHub Release...")
        self._status.setText("正在检查 GitHub Release...")
        self._worker = _CheckWorker(self)
        self._worker.succeeded.connect(self._check_succeeded)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _check_succeeded(self, release):
        self._release = release
        self._check.setEnabled(True)
        self._latest.setText(f"最新版本：{release.version}")
        self._notes.setText(f"更新说明：\n{release.notes}")
        if is_newer(release.version):
            self._phase.setText("阶段 2/3：等待下载")
            self._show_progress(value=0, detail="已找到安装包，等待开始下载。")
            self._status.setText("发现新版本，可以下载并安装。")
            self._install.setEnabled(True)
        else:
            self._phase.setText("检查完成")
            self._show_progress(value=100, detail="当前版本无需更新。")
            self._status.setText(f"当前已是最新版本（{APP_NAME} {APP_VERSION}）。")

    def download(self):
        if not self._release:
            return
        self._check.setEnabled(False)
        self._install.setEnabled(False)
        self._phase.setText("阶段 2/3：下载并校验")
        self._show_progress(value=0, detail="准备下载安装包...")
        self._status.setText("准备下载...")
        self._worker = _DownloadWorker(self._release, self)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.progress_detail.connect(self._download_progress_detail)
        self._worker.status.connect(self._download_status)
        self._worker.succeeded.connect(self._download_succeeded)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _download_succeeded(self, installer):
        self._phase.setText("阶段 3/3：启动安装并重启")
        self._show_progress(indeterminate=True, detail="下载和校验完成，正在启动安装程序...")
        self._status.setText("下载完成，正在启动安装程序。")
        launch_update(Path(installer))
        QMessageBox.information(self, "准备更新", "软件将关闭并安装新版本，安装完成后会自动重新启动。")
        self.accept()
        # Close the settings dialog and the main window so the updater can
        # replace the running installation cleanly.
        window = self.parent()
        while window is not None and window.parentWidget() is not None:
            window = window.parentWidget()
        if window is not None:
            window.close()

    def _failed(self, message):
        self._check.setEnabled(True)
        self._phase.setText("更新失败")
        self._progress.setVisible(False)
        self._progress_detail.setVisible(False)
        self._status.setText("更新失败，请检查网络或稍后重试。")
        QMessageBox.warning(self, "更新失败", message)

    def _show_progress(self, *, value=None, indeterminate=False, detail=""):
        self._progress.setVisible(True)
        self._progress_detail.setVisible(True)
        if indeterminate:
            self._progress.setRange(0, 0)
            self._progress.setFormat("处理中…")
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(max(0, min(100, int(value or 0))))
            self._progress.setFormat("%p%")
        if detail:
            self._progress_detail.setText(detail)

    def _download_progress_detail(self, completed, total):
        def format_size(value):
            units = ("B", "KB", "MB", "GB")
            amount = float(max(0, value))
            for unit in units:
                if amount < 1024 or unit == units[-1]:
                    return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
                amount /= 1024

        if total > 0:
            self._progress_detail.setText(
                f"{self._last_download_status}  已下载 {format_size(completed)} / {format_size(total)}"
            )
        else:
            self._progress_detail.setText(
                f"{self._last_download_status}  已下载 {format_size(completed)}"
            )

    def _download_status(self, message):
        self._last_download_status = str(message)
        self._status.setText(self._last_download_status)
