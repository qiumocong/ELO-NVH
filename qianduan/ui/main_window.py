"""
主窗口模块

布局结构：
┌──────────────────────────────────────────┐
│  StatusBarWidget（连接状态指示灯）         │
├──────────────┬─────────────┬─────────────┤
│  工件 ID      │  X 时域图    │  X 频谱图   │
│  [模型选择▼]  ├─────────────┼─────────────┤
│  [确认]       │  Y 时域图    │  Y 频谱图   │
│              ├─────────────┼─────────────┤
│ ┌──────────┐ │  Z 时域图    │  Z 频谱图   │
│ │ 检测结果  │ ├─────────────┴─────────────┤
│ │ (醒目大字)│ │  电流时域图               │
│ └──────────┘ │                           │
└──────────────┴───────────────────────────┘
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from config import CHANNELS, VIBRATION_CHANNELS
from ui.status_bar import StatusBarWidget
from ui.time_chart import TimeChart
from ui.spectrum_chart import SpectrumChart
from ui.result_panel import ResultPanel


class MainWindow(QMainWindow):
    """主窗口：组装所有组件，连接信号"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("XXX 检测系统")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)

        self._charts = {}
        self._spectrum_charts = {}
        self._data_started = False
        self._source = None

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

        # --- 左侧面板：工件ID + 模型选择 + 检测结果 ---
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_panel.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #e0e0e0;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 20, 12, 12)
        left_layout.setSpacing(10)

        # 工件 ID
        self._obj_label = QLabel("工件 ID: ——")
        self._obj_label.setFixedHeight(40)
        self._obj_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        left_layout.addWidget(self._obj_label)

        # 模型选择
        model_label = QLabel("选择模型:")
        model_label.setStyleSheet("font-size: 14px; color: #555;")
        left_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setFixedHeight(36)
        self._model_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                font-size: 14px;
            }
        """)
        left_layout.addWidget(self._model_combo)

        self._confirm_btn = QPushButton("确认")
        self._confirm_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                background-color: #4A90D9;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #357ABD; }
        """)
        self._confirm_btn.clicked.connect(self._on_confirm)
        left_layout.addWidget(self._confirm_btn)

        # 分隔线
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #ddd;")
        left_layout.addWidget(sep2)

        # 检测结果（占据剩余空间）
        self._result_panel = ResultPanel()
        left_layout.addWidget(self._result_panel)

        content_layout.addWidget(left_panel)

        # --- 右侧图表区：4 行布局 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        for ch in VIBRATION_CHANNELS:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            time_chart = TimeChart(ch)
            self._charts[ch] = time_chart
            row_layout.addWidget(time_chart, stretch=1)

            spectrum_chart = SpectrumChart(ch)
            self._spectrum_charts[ch] = spectrum_chart
            row_layout.addWidget(spectrum_chart, stretch=1)

            right_layout.addWidget(row, stretch=1)

        current_chart = TimeChart("current")
        self._charts["current"] = current_chart
        right_layout.addWidget(current_chart, stretch=1)

        content_layout.addWidget(right_panel, stretch=1)
        main_layout.addWidget(content, stretch=1)

    def _on_confirm(self):
        model = self._model_combo.currentText()
        if model and self._source:
            self._source.send_model(model)

    def connect_data_source(self, source):
        self._source = source
        source.data_received.connect(self._on_data)
        source.result_received.connect(self._on_result)
        source.obj_id_received.connect(self._on_obj_id)
        source.model_list_received.connect(self._on_model_list)
        source.connection_changed.connect(self._on_connection_changed)

    def _on_data(self, msg: dict):
        """
        处理接收到的传感器数据。

        数据格式有两种：
        1. 单点：{"timestamp": 0.012, "x": 0.21, "y": -0.13, ...}
        2. 批量：{"time": [0.001, 0.002, ...], "x": [0.12, 0.15, ...], ...}
        """
        # 第一次收到数据时，更新检测状态为"检测中"
        if not self._data_started:
            self._data_started = True
            self._status_bar.set_detect_status("检测中")

        times = msg.get("time", [])
        if not times:
            # --- 单点数据 ---
            t = msg.get("timestamp", 0)
            times = [t]
            for ch in CHANNELS:
                val = msg.get(ch)
                if val is not None:
                    self._charts[ch].add_data([t], [val])
        else:
            # --- 批量数据 ---
            for ch in CHANNELS:
                values = msg.get(ch, [])
                if values:
                    self._charts[ch].add_data(times, values)

        # --- 更新频谱图 ---
        # 取每个振动通道的最新数据做 FFT
        for ch in VIBRATION_CHANNELS:
            chart = self._charts[ch]
            if len(chart._values) >= 16:  # 至少 16 个点才能做有意义的 FFT
                self._spectrum_charts[ch].update_from_time_data(list(chart._values))

    def _on_result(self, msg: dict):
        """处理检测结果"""
        self._result_panel.set_result(
            msg.get("result", ""),
            msg.get("score", 0.0),
            msg.get("message", ""),
        )
        self._status_bar.set_detect_status("完成")

    def _on_obj_id(self, obj_id: str):
        self._obj_label.setText(f"工件 ID: {obj_id}")

    def _on_model_list(self, models: list):
        self._model_combo.clear()
        self._model_combo.addItems(models)

    def _on_connection_changed(self, connected: bool):
        """处理连接状态变化"""
        self._status_bar.set_connected(connected)
