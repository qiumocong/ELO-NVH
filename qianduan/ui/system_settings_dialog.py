"""统一的应用设置对话框。

通信、文件路径和图表显示参数在同一个窗口中维护，所有值仍然写入
``config.json``，因此与旧版配置文件保持兼容。
"""

from pathlib import Path
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app_config import ensure_directories, load, save


class SystemSettingsDialog(QDialog):
    """统一管理通信、存储和显示设置。"""

    def __init__(self, parent=None, values=None):
        super().__init__(parent)
        self.setWindowTitle("系统设置")
        self.setMinimumSize(700, 540)
        self.resize(760, 590)
        self._values = dict(values or load())
        self._build()

    @staticmethod
    def _field_label(text):
        label = QLabel(text)
        label.setMinimumWidth(138)
        return label

    @staticmethod
    def _form_layout():
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        return form

    @staticmethod
    def _group(title, form):
        group = QGroupBox(title)
        group.setLayout(form)
        return group

    def _path_row(self, form, key, label):
        edit = QLineEdit(str(self._values[key]))
        edit.setClearButtonEnabled(True)
        button = QPushButton("浏览...")
        button.setMinimumWidth(76)
        button.clicked.connect(lambda: self._browse(edit, label))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(edit, 1)
        row.addWidget(button)
        form.addRow(self._field_label(label), row)
        setattr(self, "_" + key, edit)

    @staticmethod
    def _browse(edit, label):
        path = QFileDialog.getExistingDirectory(None, f"选择{label}", edit.text())
        if path:
            edit.setText(path)

    def _build(self):
        self.setStyleSheet(
            """
            QDialog { background: #f6f8fa; }
            QTabWidget::pane { border: 1px solid #d7dee5; background: white; }
            QTabBar::tab {
                min-width: 120px; padding: 9px 18px; color: #52606d;
                background: #e9eef2; border: 1px solid #d7dee5;
                border-bottom: none;
            }
            QTabBar::tab:selected { color: #1f4e79; background: white; font-weight: bold; }
            QGroupBox {
                margin-top: 14px; padding: 18px 12px 12px;
                border: 1px solid #d7dee5; border-radius: 5px;
                background: white; font-weight: bold; color: #263746;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                min-height: 30px; padding: 2px 8px;
                border: 1px solid #c8d1da; border-radius: 3px; background: white;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #4a90d9;
            }
            QPushButton { min-height: 30px; padding: 2px 14px; }
            QLabel#hint { color: #6b7785; font-size: 12px; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        intro = QLabel("统一配置通信、数据保存和实时图表显示参数")
        intro.setObjectName("hint")
        layout.addWidget(intro)

        tabs = QTabWidget()
        tabs.addTab(self._build_connection_tab(), "通信设置")
        tabs.addTab(self._build_storage_tab(), "存储设置")
        tabs.addTab(self._build_display_tab(), "显示设置")
        layout.addWidget(tabs, 1)

        restart_hint = QLabel("保存后，通信地址、端口及后端存储路径将在下次启动时生效；显示设置立即生效。")
        restart_hint.setObjectName("hint")
        restart_hint.setWordWrap(True)
        layout.addWidget(restart_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_connection_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 16)
        form = self._form_layout()

        self._ws_url = QLineEdit(str(self._values["ws_url"]))
        self._ws_url.setPlaceholderText("例如：ws://127.0.0.1:8081")
        form.addRow(self._field_label("WebSocket 地址"), self._ws_url)

        self._reconnect = QDoubleSpinBox()
        self._reconnect.setRange(0.2, 60.0)
        self._reconnect.setDecimals(1)
        self._reconnect.setSuffix(" 秒")
        self._reconnect.setValue(float(self._values["reconnect_interval"]))
        form.addRow(self._field_label("断线重连间隔"), self._reconnect)

        self._plc_ip = QLineEdit(str(self._values["plc_ip"]))
        self._plc_ip.setPlaceholderText("例如：192.168.3.124")
        form.addRow(self._field_label("PLC 地址"), self._plc_ip)

        self._plc_port = QSpinBox()
        self._plc_port.setRange(1, 65535)
        self._plc_port.setValue(int(self._values["plc_port"]))
        form.addRow(self._field_label("PLC 端口"), self._plc_port)

        self._backend_port = QSpinBox()
        self._backend_port.setRange(1, 65535)
        self._backend_port.setValue(int(self._values["backend_port"]))
        form.addRow(self._field_label("后端 WebSocket 端口"), self._backend_port)

        layout.addWidget(self._group("设备与服务", form))
        layout.addStretch(1)
        return page

    def _build_storage_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 16)
        form = self._form_layout()
        self._path_row(form, "log_dir", "日志保存路径")
        self._path_row(form, "data_save_dir", "训练数据路径")
        self._path_row(form, "new_data_save_dir", "新格式数据路径")
        self._path_row(form, "model_dir", "模型保存路径")
        self._enable_new = QCheckBox("保存 CSV、振动图、音频等新格式数据")
        self._enable_new.setChecked(bool(self._values["enable_new_save"]))
        form.addRow(self._field_label("新格式数据"), self._enable_new)

        layout.addWidget(self._group("文件目录", form))
        hint = QLabel("建议使用本机固定磁盘目录，并确保运行账户拥有读写权限。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_display_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 16)

        axis_form = self._form_layout()
        self._y_auto = QCheckBox("自动适配当前振动数据")
        self._y_auto.setChecked(bool(self._values.get("y_axis_auto", True)))
        self._y_auto.toggled.connect(self._toggle_axis_inputs)
        axis_form.addRow(self._field_label("纵轴范围"), self._y_auto)

        self._y_min = QDoubleSpinBox()
        self._y_min.setRange(-9999.0, 9999.0)
        self._y_min.setDecimals(2)
        self._y_min.setValue(float(self._values.get("y_axis_min", -1.0)))
        axis_form.addRow(self._field_label("纵轴最小值"), self._y_min)

        self._y_max = QDoubleSpinBox()
        self._y_max.setRange(-9999.0, 9999.0)
        self._y_max.setDecimals(2)
        self._y_max.setValue(float(self._values.get("y_axis_max", 1.0)))
        axis_form.addRow(self._field_label("纵轴最大值"), self._y_max)
        layout.addWidget(self._group("振动图设置", axis_form))

        scale_form = self._form_layout()
        self._scale = QDoubleSpinBox()
        self._scale.setRange(1.0, 1000.0)
        self._scale.setDecimals(0)
        self._scale.setSuffix(" %")
        self._scale.setValue(float(self._values.get("vibration_scale", 1.0)) * 100.0)
        scale_form.addRow(self._field_label("振动数据缩放"), self._scale)
        scale_hint = QLabel("仅改变界面显示比例，不修改原始采集数据和已保存文件。")
        scale_hint.setObjectName("hint")
        scale_hint.setWordWrap(True)
        scale_form.addRow("", scale_hint)
        layout.addWidget(self._group("数据缩放", scale_form))

        layout.addStretch(1)
        self._toggle_axis_inputs(self._y_auto.isChecked())
        return page

    def _toggle_axis_inputs(self, auto):
        self._y_min.setEnabled(not auto)
        self._y_max.setEnabled(not auto)

    def _accept(self):
        ws_url = self._ws_url.text().strip()
        plc_ip = self._plc_ip.text().strip()
        paths = {
            "log_dir": self._log_dir.text().strip(),
            "data_save_dir": self._data_save_dir.text().strip(),
            "new_data_save_dir": self._new_data_save_dir.text().strip(),
            "model_dir": self._model_dir.text().strip(),
        }
        if not ws_url or not (ws_url.startswith("ws://") or ws_url.startswith("wss://")):
            QMessageBox.warning(self, "设置无效", "请输入有效的 WebSocket 地址（ws:// 或 wss://）。")
            return
        if not plc_ip:
            QMessageBox.warning(self, "设置无效", "PLC 地址不能为空。")
            return
        if any(not value for value in paths.values()):
            QMessageBox.warning(self, "设置无效", "所有文件保存路径都不能为空。")
            return

        y_min, y_max = self._y_min.value(), self._y_max.value()
        if not self._y_auto.isChecked() and y_min >= y_max:
            QMessageBox.warning(self, "设置无效", "纵轴最小值必须小于最大值。")
            return

        values = dict(self._values)
        values.update(
            {
                "ws_url": ws_url,
                "reconnect_interval": self._reconnect.value(),
                "plc_ip": plc_ip,
                "plc_port": self._plc_port.value(),
                "backend_port": self._backend_port.value(),
                **paths,
                "enable_new_save": self._enable_new.isChecked(),
                "y_axis_auto": self._y_auto.isChecked(),
                "y_axis_min": y_min,
                "y_axis_max": y_max,
                "vibration_scale": self._scale.value() / 100.0,
            }
        )
        try:
            ensure_directories(values)
            self.values = save(values)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "保存失败", f"无法保存设置：{exc}")
            return
        self.accept()
