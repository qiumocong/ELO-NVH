"""Application-level settings dialog (paths and communication endpoints)."""
from pathlib import Path

from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QPushButton, QVBoxLayout,
)

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app_config import load, save, ensure_directories


class SystemSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("系统设置")
        self.setMinimumWidth(620)
        self._values = load()
        self._build()

    def _path_row(self, form, key):
        edit = QLineEdit(str(self._values[key]))
        button = QPushButton("浏览...")
        button.clicked.connect(lambda: self._browse(edit))
        row = QHBoxLayout(); row.addWidget(edit); row.addWidget(button)
        form.addRow({"log_dir": "日志保存路径", "data_save_dir": "训练数据路径",
                     "new_data_save_dir": "新格式数据路径", "model_dir": "模型路径"}[key], row)
        setattr(self, "_" + key, edit)

    @staticmethod
    def _browse(edit):
        path = QFileDialog.getExistingDirectory(None, "选择目录", edit.text())
        if path:
            edit.setText(path)

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._ws_url = QLineEdit(str(self._values["ws_url"]))
        form.addRow("WebSocket 地址", self._ws_url)
        self._reconnect = QDoubleSpinBox(); self._reconnect.setRange(0.2, 60); self._reconnect.setValue(float(self._values["reconnect_interval"]))
        form.addRow("断线重连间隔(秒)", self._reconnect)
        self._plc_ip = QLineEdit(str(self._values["plc_ip"])); form.addRow("PLC 地址", self._plc_ip)
        self._plc_port = QSpinBox(); self._plc_port.setRange(1, 65535); self._plc_port.setValue(int(self._values["plc_port"])); form.addRow("PLC 端口", self._plc_port)
        self._backend_port = QSpinBox(); self._backend_port.setRange(1, 65535); self._backend_port.setValue(int(self._values["backend_port"])); form.addRow("后端 WebSocket 端口", self._backend_port)
        for key in ("log_dir", "data_save_dir", "new_data_save_dir", "model_dir"):
            self._path_row(form, key)
        self._enable_new = QCheckBox("启用新格式数据保存（CSV、图片、音频）")
        self._enable_new.setChecked(bool(self._values["enable_new_save"]))
        form.addRow("数据保存", self._enable_new)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        values = dict(self._values)
        values.update({"ws_url": self._ws_url.text().strip(), "reconnect_interval": self._reconnect.value(),
                       "plc_ip": self._plc_ip.text().strip(), "plc_port": self._plc_port.value(),
                       "backend_port": self._backend_port.value(), "enable_new_save": self._enable_new.isChecked()})
        for key in ("log_dir", "data_save_dir", "new_data_save_dir", "model_dir"):
            values[key] = getattr(self, "_" + key).text().strip()
        if not values["ws_url"] or not values["plc_ip"] or any(not values[k] for k in ("log_dir", "data_save_dir", "new_data_save_dir", "model_dir")):
            return
        ensure_directories(values); save(values)
        self.values = values
        self.accept()

