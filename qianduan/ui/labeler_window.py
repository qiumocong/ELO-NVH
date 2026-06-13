"""
数据集标注主窗口

作用：提供人工标注界面，用于制作训练数据集。

和 MainWindow 的区别：
- 没有模型选择（不需要选模型）
- 没有工件 ID 显示（标注时不需要）
- 左侧面板改为人工标注按钮（合格/不合格）
- 保留所有时域曲线和频谱图（人工观察用）
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame
)
from PyQt5.QtCore import Qt
from config import CHANNELS, VIBRATION_CHANNELS
from ui.status_bar import StatusBarWidget
from ui.time_chart import TimeChart
from ui.spectrum_chart import SpectrumChart
from ui.labeler_panel import LabelerPanel


class LabelerWindow(QMainWindow):
    """数据集标注主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据集标注工具")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)

        self._charts = {}
        self._spectrum_charts = {}
        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 状态栏（连接状态 + 检测状态改为"标注模式"）---
        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        main_layout.addWidget(sep)

        # --- 主内容区 ---
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- 左侧：标注面板 ---
        left_panel = QWidget()
        left_panel.setFixedWidth(200)
        left_panel.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #e0e0e0;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 12, 8, 12)

        self._labeler_panel = LabelerPanel()
        left_layout.addWidget(self._labeler_panel)

        content_layout.addWidget(left_panel)

        # --- 右侧：图表区 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        # 时域图行
        time_row = QWidget()
        time_layout = QHBoxLayout(time_row)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(6)
        for ch in CHANNELS:
            chart = TimeChart(ch)
            self._charts[ch] = chart
            time_layout.addWidget(chart)
        right_layout.addWidget(time_row, stretch=3)

        # 频谱图行
        spectrum_row = QWidget()
        spectrum_layout = QHBoxLayout(spectrum_row)
        spectrum_layout.setContentsMargins(0, 0, 0, 0)
        spectrum_layout.setSpacing(6)
        for ch in VIBRATION_CHANNELS:
            chart = SpectrumChart(ch)
            self._spectrum_charts[ch] = chart
            spectrum_layout.addWidget(chart)
        placeholder = QWidget()
        spectrum_layout.addWidget(placeholder)
        right_layout.addWidget(spectrum_row, stretch=2)

        content_layout.addWidget(right_panel, stretch=1)
        main_layout.addWidget(content, stretch=1)

    def connect_data_source(self, source):
        """连接数据源"""
        source.data_received.connect(self._on_data)
        source.connection_changed.connect(self._on_connection_changed)
        # 用户标注后，发送标签给数据源（数据源负责转发给后端）
        self._labeler_panel.label_submitted.connect(source.send_label)

    def _on_data(self, msg: dict):
        """处理传感器数据（和 MainWindow 一样）"""
        times = msg.get("time", [])
        if not times:
            t = msg.get("timestamp", 0)
            times = [t]
            for ch in CHANNELS:
                val = msg.get(ch)
                if val is not None:
                    self._charts[ch].add_data([t], [val])
        else:
            for ch in CHANNELS:
                values = msg.get(ch, [])
                if values:
                    self._charts[ch].add_data(times, values)

        # 更新频谱图
        for ch in VIBRATION_CHANNELS:
            chart = self._charts[ch]
            if len(chart._values) >= 16:
                self._spectrum_charts[ch].update_from_time_data(list(chart._values))

    def _on_connection_changed(self, connected: bool):
        self._status_bar.set_connected(connected)
        if connected:
            self._status_bar.set_detect_status("标注模式")
