"""
数据集标注主窗口 — 双组数据版本

布局结构：
┌─────────────────────────────────────────────────────────────────┐
│  StatusBarWidget                                                  │
├──────────┬─────────────────────┬─────────────────────────────────┤
│ 左侧标注  │ 左X时域 │ 左X频谱   │ 右X时域 │ 右X频谱               │
│ [合格]    ├─────────────────────┼─────────────────────────────────┤
│ [不合格]  │ 左Y时域 │ 左Y频谱   │ 右Y时域 │ 右Y频谱               │
│ [确认]    ├─────────────────────┼─────────────────────────────────┤
│          │ 左Z时域 │ 左Z频谱   │ 右Z时域 │ 右Z频谱               │
│ ──────── ├─────────────────────┼─────────────────────────────────┤
│ 右侧标注  │ 左电流              │ 右电流                           │
│ [合格]    │                     │                                   │
│ [不合格]  │                     │                                   │
│ [确认]    │                     │                                   │
└──────────┴─────────────────────┴─────────────────────────────────┘
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame
)
from config import VIBRATION_CHANNELS
from ui.status_bar import StatusBarWidget
from ui.time_chart import TimeChart
from ui.spectrum_chart import SpectrumChart
from ui.labeler_panel import LabelerPanel

SIDES = ["left", "right"]
ALL_CHANNELS = ["x", "y", "z", "current"]


class LabelerWindow(QMainWindow):
    """数据集标注主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据集标注工具")
        self.setMinimumSize(1400, 800)
        self.resize(1600, 900)

        self._charts = {side: {} for side in SIDES}
        self._spectrum_charts = {side: {} for side in SIDES}

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 状态栏 ---
        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        main_layout.addWidget(sep)

        # --- 主内容区 ---
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ========== 左侧面板：双标注面板 ==========
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_panel.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #e0e0e0;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 20, 12, 12)
        left_layout.setSpacing(4)

        # 左侧标注面板
        self._labeler_left = LabelerPanel("left")
        left_layout.addWidget(self._labeler_left, stretch=1)

        # 分隔
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #ccc;")
        left_layout.addWidget(sep2)

        # 右侧标注面板
        self._labeler_right = LabelerPanel("right")
        left_layout.addWidget(self._labeler_right, stretch=1)

        content_layout.addWidget(left_panel)

        # ========== 右侧图表区：双组 4 行 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        # X/Y/Z 三行：每行 左时域+左频谱 | 右时域+右频谱
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

        # 电流行：左电流 | 右电流
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

    def connect_data_source(self, source):
        source.data_received.connect(self._on_data)
        source.connection_changed.connect(self._on_connection_changed)
        self._labeler_left.label_submitted.connect(source.send_label)
        self._labeler_right.label_submitted.connect(source.send_label)

    def _on_data(self, msg: dict):
        times = msg.get("time", [])
        if not times:
            t = msg.get("timestamp", 0)
            times = [t]
            for side in SIDES:
                for ch in ALL_CHANNELS:
                    val = msg.get(f"{side}_{ch}")
                    if val is not None:
                        self._charts[side][ch].add_data([t], [val])
        else:
            for side in SIDES:
                for ch in ALL_CHANNELS:
                    values = msg.get(f"{side}_{ch}", [])
                    if values:
                        self._charts[side][ch].add_data(times, values)

        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                chart = self._charts[side][ch]
                if len(chart._values) >= 16:
                    self._spectrum_charts[side][ch].update_from_time_data(list(chart._values))

    def _on_connection_changed(self, connected: bool):
        self._status_bar.set_connected(connected)
        if connected:
            self._status_bar.set_detect_status("标注模式")
