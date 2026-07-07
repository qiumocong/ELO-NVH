"""
主窗口模块 — 双工位纯展示版

布局结构：
┌─────────────────────────────────────────────────────────────────┐
├──────────┬─────────────────────┬─────────────────────────────────┤
│ 左工位    │ 左X时域 │ 左X频谱   │ 右X时域 │ 右X频谱               │
│ 右工位    ├─────────────────────┼─────────────────────────────────┤
│ ────────  │ 左Y时域 │ 左Y频谱   │ 右Y时域 │ 右Y频谱               │
│ 连接状态   ├─────────────────────┼─────────────────────────────────┤
│ 检测状态   │ 左Z时域 │ 左Z频谱   │ 右Z时域 │ 右Z频谱               │
│ ────────  ├─────────────────────┼─────────────────────────────────┤
│ 左结果    │ 左电流              │ 右电流                           │
│ 右结果    │                     │                                   │
└──────────┴─────────────────────┴─────────────────────────────────┘
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QFrame
)
from PyQt5.QtCore import Qt
from config import VIBRATION_CHANNELS
from ui.status_bar import StatusBarWidget
from ui.time_chart import TimeChart
from ui.spectrum_chart import SpectrumChart
from ui.result_panel import ResultPanel
from ui.settings_dialog import SettingsDialog
from ui.scale_dialog import ScaleDialog

SIDES = ["left", "right"]
ALL_CHANNELS = ["x", "y", "z", "current"]

SIDE_TITLES = {"left": "左工位", "right": "右工位"}


class MainWindow(QMainWindow):
    """主窗口：双工位信息 + 双推理结果"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("XXX 检测系统")
        self.setMinimumSize(1400, 800)
        self.resize(1600, 900)

        self._charts = {side: {} for side in SIDES}
        self._spectrum_charts = {side: {} for side in SIDES}
        self._data_started = False
        self._source = None
        self._spectrum_tick = 0
        self._side_has_data = {"left": False, "right": False}
        self._side_next_time = {"left": 0.0, "right": 0.0}
        self._vib_scale = 1.0  # 振动数据缩放比例

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 主内容区
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

        # 工位信息：左 + 右
        self._info_frames = {}
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
            self._info_frames[side] = frame
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

        # 左检测结果
        self._result_panel_left = ResultPanel("左侧检测结果")
        left_layout.addWidget(self._result_panel_left, stretch=1)

        # 右检测结果
        self._result_panel_right = ResultPanel("右侧检测结果")
        left_layout.addWidget(self._result_panel_right, stretch=1)

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

    def _clear_side(self, side: str):
        """清空指定侧的图表和结果"""
        for ch in ALL_CHANNELS:
            self._charts[side][ch].clear()
        for ch in VIBRATION_CHANNELS:
            self._spectrum_charts[side][ch].clear()
        if side == "left":
            self._result_panel_left.clear()
        else:
            self._result_panel_right.clear()
        self._side_has_data[side] = False
        self._side_next_time[side] = 0.0
        self._data_started = False
        self._spectrum_tick = 0

    def _on_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec_() != dlg.Accepted:
            return

        if dlg.auto_mode:
            # 恢复自动范围
            for side in SIDES:
                for ch in VIBRATION_CHANNELS:
                    self._charts[side][ch]._plot_widget.enableAutoRange(y=True)
            return

        y_min, y_max = dlg.values
        if y_min >= y_max:
            return

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
        # 已有数据原地缩放，不清空
        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                chart = self._charts[side][ch]
                if chart._values:
                    chart._values = [v * ratio for v in chart._values]
                    chart._update_plot()
        # 频谱重新累积
        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                self._spectrum_charts[side][ch].clear()

    def connect_data_source(self, source):
        self._source = source
        source.data_received.connect(self._on_data)
        source.result_received.connect(self._on_result)
        source.info_received.connect(self._on_info)
        source.model_list_received.connect(self._on_model_list)
        source.connection_changed.connect(self._on_connection_changed)

    def _on_data(self, msg: dict):
        if not self._data_started:
            self._data_started = True
            self._status_bar.set_detect_status("检测中")
        times = msg.get("time", [])
        if not times:
            for side in SIDES:
                for ch in ALL_CHANNELS:
                    val = msg.get(f"{side}_{ch}")
                    if val is not None:
                        t0 = self._side_next_time[side]
                        self._side_next_time[side] = t0 + 1.0 / 4800
                        self._charts[side][ch].add_data([t0], [val])
        else:
            for side in SIDES:
                has = False
                for ch in ALL_CHANNELS:
                    values = msg.get(f"{side}_{ch}", [])
                    if values:
                        # 各侧独立生成连续时间，不依赖后端共享的 time 数组
                        t0 = self._side_next_time[side]
                        if times and len(times) > 1:
                            dt = (times[-1] - times[0]) / (len(times) - 1)
                        else:
                            dt = 1.0 / 4800  # fallback
                        n = len(values)
                        local_times = [t0 + i * dt for i in range(n)]
                        self._side_next_time[side] = local_times[-1] + dt
                        # 振动通道应用缩放，电流不变
                        if ch in VIBRATION_CHANNELS and self._vib_scale != 1.0:
                            values = [v * self._vib_scale for v in values]
                        self._charts[side][ch].add_data(local_times, values)
                        has = True
                if has:
                    self._side_has_data[side] = True
        # 频谱图每 200ms 更新一次，减少全量数据拷贝和渲染压力
        self._spectrum_tick += 1
        if self._spectrum_tick % 4 == 0:
            for side in SIDES:
                for ch in VIBRATION_CHANNELS:
                    chart = self._charts[side][ch]
                    if len(chart._values) >= 64:
                        self._spectrum_charts[side][ch].update_from_time_data(
                            chart._values, chart._times)

    def _on_result(self, msg: dict):
        result_text = msg.get("result", "")
        score = msg.get("score", 0.0)
        message = msg.get("message", "")
        side = msg.get("side", "left")
        if side == "right":
            self._result_panel_right.set_result(result_text, score, message)
        else:
            self._result_panel_left.set_result(result_text, score, message)
        self._status_bar.set_detect_status("完成")

    def _on_info(self, msg: dict):
        side = msg.get("side", "left")
        labels = self._info_labels.get(side)
        if not labels:
            return
        barcode = msg.get("barcode", msg.get("obj_id", "——"))
        spec = msg.get("spec", "——")
        mode = msg.get("mode", "——")
        mode_display = {"auto": "自动", "manual": "人工"}.get(mode, mode)

        # 如果该侧已有数据，说明是新的一轮检测，自动清空该侧
        if self._side_has_data.get(side):
            self._clear_side(side)

        labels["barcode"].setText(f"条码: {barcode}")
        labels["spec"].setText(f"规格: {spec}")
        labels["mode"].setText(f"模式: {mode_display}")

    def _on_model_list(self, models: list):
        pass  # 前端不需要选模型，仅接收

    def _on_connection_changed(self, connected: bool):
        self._status_bar.set_connected(connected)
