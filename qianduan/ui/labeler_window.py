"""
数据集标注主窗口 — 双组数据版本
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
)
from PyQt5.QtCore import Qt
from config import VIBRATION_CHANNELS
from ui.status_bar import StatusBarWidget
from ui.time_chart import TimeChart
from ui.spectrum_chart import SpectrumChart
from ui.labeler_panel import LabelerPanel
from ui.settings_dialog import SettingsDialog
from ui.scale_dialog import ScaleDialog
from ui.system_settings_dialog import SystemSettingsDialog
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app_config import load as load_runtime_config, save as save_runtime_config

SIDES = ["left", "right"]
ALL_CHANNELS = ["x", "y", "z", "current"]
SIDE_TITLES = {"left": "左工位", "right": "右工位"}


class LabelerWindow(QMainWindow):
    """数据集标注主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据集标注工具")
        self.setMinimumSize(1400, 800)
        self.resize(1600, 900)

        self._charts = {side: {} for side in SIDES}
        self._spectrum_charts = {side: {} for side in SIDES}
        self._spectrum_tick = 0
        self._side_has_data = {"left": False, "right": False}
        self._side_next_time = {"left": 0.0, "right": 0.0}
        self._vib_scale = 1.0
        self._runtime_config = load_runtime_config()
        self._vib_scale = float(self._runtime_config.get("vibration_scale", 1.0))
        self._last_batch_id = {"left": -1, "right": -1}
        self._diag_rx_count = 0
        self._diag_rx_dup = 0
        self._diag_start_time = None

        self._setup_ui()
        self._restore_visual_settings()

    def _restore_visual_settings(self):
        cfg = self._runtime_config
        if cfg.get("y_axis_auto", True):
            return
        y_min, y_max = float(cfg.get("y_axis_min", -1.0)), float(cfg.get("y_axis_max", 1.0))
        if y_min >= y_max:
            return
        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                self._charts[side][ch]._plot_widget.setYRange(y_min, y_max)
                self._charts[side][ch]._plot_widget.enableAutoRange(y=False)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ========== 左侧面板 ==========
        left_panel = QWidget()
        left_panel.setFixedWidth(320)
        left_panel.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #e0e0e0;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 20, 12, 12)
        left_layout.setSpacing(8)

        # 工位信息
        self._info_labels = {}
        for side in SIDES:
            frame = QFrame()
            frame.setFrameShape(QFrame.StyledPanel)
            frame.setStyleSheet("""
                QFrame {
                    background-color: #f0f4f8;
                    border: 1px solid #d0d8e0;
                    border-radius: 6px;
                    padding: 6px;
                }
            """)
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 6, 8, 6)
            fl.setSpacing(2)

            title = QLabel(SIDE_TITLES[side])
            title.setStyleSheet("font-size: 13px; font-weight: bold; color: #333;")
            fl.addWidget(title)

            barcode = QLabel("条码: ——")
            barcode.setStyleSheet("font-size: 12px; color: #555;")
            fl.addWidget(barcode)

            spec = QLabel("规格: ——")
            spec.setStyleSheet("font-size: 12px; color: #555;")
            fl.addWidget(spec)

            mode = QLabel("模式: ——")
            mode.setStyleSheet("font-size: 12px; color: #555;")
            fl.addWidget(mode)

            self._info_labels[side] = {"barcode": barcode, "spec": spec, "mode": mode}
            left_layout.addWidget(frame)

        # 分隔
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #ccc;")
        left_layout.addWidget(sep2)

        # 连接状态 + 检测状态
        self._status_bar = StatusBarWidget()
        left_layout.addWidget(self._status_bar)

        # 设置按钮
        from PyQt5.QtWidgets import QPushButton
        self._settings_btn = QPushButton("振动图设置")
        self._settings_btn.setFixedHeight(32)
        self._settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B; color: white;
                border: none; border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #546E7A; }
        """)
        self._settings_btn.clicked.connect(self._on_settings)
        left_layout.addWidget(self._settings_btn)

        # 数据缩放按钮
        self._scale_btn = QPushButton("数据缩放")
        self._scale_btn.setFixedHeight(32)
        self._scale_btn.setStyleSheet("""
            QPushButton {
                background-color: #795548; color: white;
                border: none; border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #6D4C41; }
        """)
        self._scale_btn.clicked.connect(self._on_scale_settings)
        left_layout.addWidget(self._scale_btn)

        self._system_settings_btn = QPushButton("系统设置")
        self._system_settings_btn.setFixedHeight(32)
        self._system_settings_btn.clicked.connect(self._on_system_settings)
        left_layout.addWidget(self._system_settings_btn)

        # 左侧标注面板
        self._labeler_left = LabelerPanel("left")
        left_layout.addWidget(self._labeler_left, stretch=1)

        # 分隔
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("color: #ccc;")
        left_layout.addWidget(sep3)

        # 右侧标注面板
        self._labeler_right = LabelerPanel("right")
        left_layout.addWidget(self._labeler_right, stretch=1)

        content_layout.addWidget(left_panel)

        # ========== 右侧图表区：双组 4 行 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        for ch in VIBRATION_CHANNELS:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            for side in SIDES:
                time_chart = TimeChart(f"{side}_{ch}")
                self._charts[side][ch] = time_chart
                row_layout.addWidget(time_chart, stretch=1)
                spectrum_chart = SpectrumChart(f"{side}_{ch}")
                self._spectrum_charts[side][ch] = spectrum_chart
                row_layout.addWidget(spectrum_chart, stretch=1)
            right_layout.addWidget(row, stretch=1)

        current_row = QWidget()
        current_layout = QHBoxLayout(current_row)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.setSpacing(6)
        for side in SIDES:
            chart = TimeChart(f"{side}_current")
            self._charts[side]["current"] = chart
            current_layout.addWidget(chart, stretch=1)
        right_layout.addWidget(current_row, stretch=1)

        content_layout.addWidget(right_panel, stretch=1)
        main_layout.addWidget(content, stretch=1)

    def _on_settings(self):
        cfg = self._runtime_config
        dlg = SettingsDialog(self, cfg.get("y_axis_min", -1.0), cfg.get("y_axis_max", 1.0))
        if dlg.exec_() != dlg.Accepted:
            return
        if dlg.auto_mode:
            self._runtime_config["y_axis_auto"] = True
            save_runtime_config(self._runtime_config)
            for side in SIDES:
                for ch in VIBRATION_CHANNELS:
                    self._charts[side][ch]._plot_widget.enableAutoRange(y=True)
            return
        y_min, y_max = dlg.values
        if y_min >= y_max:
            return
        self._runtime_config.update({"y_axis_auto": False, "y_axis_min": y_min, "y_axis_max": y_max})
        save_runtime_config(self._runtime_config)
        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                self._charts[side][ch]._plot_widget.setYRange(y_min, y_max)
                self._charts[side][ch]._plot_widget.enableAutoRange(y=False)

    def _on_scale_settings(self):
        dlg = ScaleDialog(self, self._vib_scale * 100)
        if dlg.exec_() != dlg.Accepted:
            return
        new_scale = dlg.scale_factor
        if new_scale == self._vib_scale:
            return
        ratio = new_scale / self._vib_scale
        self._vib_scale = new_scale
        self._runtime_config["vibration_scale"] = new_scale
        save_runtime_config(self._runtime_config)
        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                chart = self._charts[side][ch]
                if chart._values:
                    chart._values = [v * ratio for v in chart._values]
                    chart._update_plot()
        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                self._spectrum_charts[side][ch].clear()

    def _on_system_settings(self):
        dlg = SystemSettingsDialog(self)
        if dlg.exec_() == dlg.Accepted:
            self._runtime_config = dlg.values

    def _clear_side(self, side: str):
        for ch in ALL_CHANNELS:
            self._charts[side][ch].clear()
        for ch in VIBRATION_CHANNELS:
            self._spectrum_charts[side][ch].clear()
        if side == "left":
            self._labeler_left.clear()
        else:
            self._labeler_right.clear()
        self._side_has_data[side] = False
        self._side_next_time[side] = 0.0
        self._last_batch_id[side] = -1
        self._spectrum_tick = 0

    def connect_data_source(self, source):
        source.data_received.connect(self._on_data)
        source.result_received.connect(self._on_result)
        source.info_received.connect(self._on_info)
        source.connection_changed.connect(self._on_connection_changed)
        self._labeler_left.label_submitted.connect(source.send_label)
        self._labeler_right.label_submitted.connect(source.send_label)

    def _on_data(self, msg: dict):
        times = msg.get("time", [])
        if times and len(times) > 1:
            dt = (times[-1] - times[0]) / (len(times) - 1)
        else:
            dt = 1.0 / 2400
        # 诊断
        if self._diag_start_time is None:
            import time as _diag_time
            self._diag_start_time = _diag_time.monotonic()
        self._diag_rx_count += 1
        if not times:
            for side in SIDES:
                has = False
                t0 = self._side_next_time[side]
                for ch in ALL_CHANNELS:
                    val = msg.get(f"{side}_{ch}")
                    if val is not None:
                        self._charts[side][ch].add_data([t0], [val])
                        has = True
                if has:
                    self._side_next_time[side] = t0 + 1.0 / 2400
        else:
            for side in SIDES:
                bid = msg.get(f"{side}_batch_id", -1)
                if bid == self._last_batch_id[side] and bid != -1:
                    self._diag_rx_dup += 1
                    continue
                self._last_batch_id[side] = bid
                has = False
                max_n = 0
                t0 = self._side_next_time[side]
                for ch in ALL_CHANNELS:
                    values = msg.get(f"{side}_{ch}", [])
                    if values:
                        n = len(values)
                        max_n = max(max_n, n)
                        local_times = [t0 + i * dt for i in range(n)]
                        if ch in VIBRATION_CHANNELS and self._vib_scale != 1.0:
                            scaled = [v * self._vib_scale for v in values]
                            self._charts[side][ch].add_data(local_times, scaled)
                        else:
                            self._charts[side][ch].add_data(local_times, values)
                        has = True
                if has:
                    self._side_next_time[side] = t0 + max_n * dt
                    self._side_has_data[side] = True

        self._spectrum_tick += 1
        if self._spectrum_tick % 4 == 0:
            for side in SIDES:
                for ch in VIBRATION_CHANNELS:
                    chart = self._charts[side][ch]
                    if len(chart._values) >= 64:
                        self._spectrum_charts[side][ch].update_from_time_data(
                            chart._values, chart._times)
        if self._diag_rx_count % 50 == 0:
            import time as _diag_time
            elapsed = _diag_time.monotonic() - self._diag_start_time
            print(f"[标注诊断] rx={self._diag_rx_count} dup={self._diag_rx_dup} "
                  f"elapsed={elapsed:.1f}s L_time={self._side_next_time['left']:.2f}s "
                  f"R_time={self._side_next_time['right']:.2f}s")

    def _on_info(self, msg: dict):
        side = msg.get("side", "left")
        labels = self._info_labels.get(side)
        if not labels:
            return
        barcode = msg.get("barcode", msg.get("obj_id", "——"))
        spec = msg.get("spec", "——")
        mode = msg.get("mode", "——")
        mode_display = {"auto": "自动", "manual": "人工"}.get(mode, mode)

        if self._side_has_data.get(side):
            self._clear_side(side)

        labels["barcode"].setText(f"条码: {barcode}")
        labels["spec"].setText(f"规格: {spec}")
        labels["mode"].setText(f"模式: {mode_display}")

    def _on_result(self, msg: dict):
        side = msg.get("side", "left")
        result_text = msg.get("result", "")
        if side == "right":
            self._labeler_right._status_label.setText(f"后端: {result_text}")
        else:
            self._labeler_left._status_label.setText(f"后端: {result_text}")

    def _on_connection_changed(self, connected: bool):
        self._status_bar.set_connected(connected)
        if connected:
            self._status_bar.set_detect_status("标注模式")
