"""
主窗口模块

作用：把所有界面组件拼装在一起，处理数据的接收和分发。

这个文件是整个界面的"总指挥"：
- 创建所有子组件（顶部栏、状态栏、图表、结果面板）
- 定义布局（谁在左边、谁在右边、谁在上面）
- 接收数据源的信号，分发给对应的组件更新

布局结构：
┌─────────────────────────────────────────┐
│  HeaderWidget（工件ID + 模型选择）        │  ← 第一行
│  StatusBarWidget（连接状态指示灯）        │  ← 第二行
├────────────┬────────────────────────────┤
│            │  x时域  y时域  z时域  电流时域 │  ← 时域曲线行
│  Result    │                            │
│  Panel     │  x频谱  y频谱  z频谱   (空)  │  ← 频谱图行
│  (检测结果) │                            │
└────────────┴────────────────────────────┘
  ← 左侧窄栏 →  ← 右侧图表区（自动拉伸） →
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QGridLayout, QFrame, QSplitter
)
from PyQt5.QtCore import Qt, QTimer
from config import CHANNELS, VIBRATION_CHANNELS, FFT_WINDOW_SIZE
from ui.header_widget import HeaderWidget
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

        # 用字典存储图表组件，方便通过通道名访问
        # 比如 self._charts["x"] 就是 X 方向的时域图
        self._charts = {}          # 时域图：{"x": TimeChart, "y": TimeChart, ...}
        self._spectrum_charts = {} # 频谱图：{"x": SpectrumChart, "y": SpectrumChart, ...}
        self._data_started = False  # 标记数据是否已开始推送

        self._setup_ui()

    def _setup_ui(self):
        """创建并排列所有界面组件"""

        # --- 创建中心容器 ---
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)  # 垂直布局（从上到下排列）
        main_layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距
        main_layout.setSpacing(0)  # 去掉组件间距

        # --- 第一行：顶部栏（工件ID + 模型选择）---
        self._header = HeaderWidget()
        main_layout.addWidget(self._header)

        # --- 第二行：状态栏（连接状态指示灯）---
        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

        # --- 分隔线 ---
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)  # 水平线
        sep.setStyleSheet("color: #ddd;")
        main_layout.addWidget(sep)

        # --- 第三行：主内容区（左侧信息栏 + 右侧图表区）---
        content = QWidget()
        content_layout = QHBoxLayout(content)  # 水平布局（从左到右排列）
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- 左侧窄栏：检测结果 ---
        left_panel = QWidget()
        left_panel.setFixedWidth(200)  # 固定宽度 200 像素
        left_panel.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #e0e0e0;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 12, 8, 12)

        self._result_panel = ResultPanel()
        left_layout.addWidget(self._result_panel)

        content_layout.addWidget(left_panel)

        # --- 右侧图表区 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)  # 垂直布局：上面时域图，下面频谱图
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        # --- 时域图行：4 个图并排 ---
        time_row = QWidget()
        time_layout = QHBoxLayout(time_row)  # 水平布局：4 个图从左到右
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(6)
        for ch in CHANNELS:  # CHANNELS = ["x", "y", "z", "current"]
            chart = TimeChart(ch)
            self._charts[ch] = chart  # 存到字典里，后面更新数据要用
            time_layout.addWidget(chart)
        right_layout.addWidget(time_row, stretch=3)  # stretch=3 表示占 3 份高度

        # --- 频谱图行：3 个图并排 + 1 个空占位 ---
        spectrum_row = QWidget()
        spectrum_layout = QHBoxLayout(spectrum_row)
        spectrum_layout.setContentsMargins(0, 0, 0, 0)
        spectrum_layout.setSpacing(6)
        for ch in VIBRATION_CHANNELS:  # VIBRATION_CHANNELS = ["x", "y", "z"]
            chart = SpectrumChart(ch)
            self._spectrum_charts[ch] = chart
            spectrum_layout.addWidget(chart)
        # 电流不需要频谱图，放一个空白占位，保持布局对齐
        placeholder = QWidget()
        spectrum_layout.addWidget(placeholder)
        right_layout.addWidget(spectrum_row, stretch=2)  # stretch=2 表示占 2 份高度

        content_layout.addWidget(right_panel, stretch=1)
        main_layout.addWidget(content, stretch=1)

    def connect_data_source(self, source):
        """
        把数据源（MockDataSource 或 WebSocketClient）的信号连接到窗口的槽函数。

        信号-槽机制是 PyQt5 的核心：
        - 数据源"发射"信号（比如 data_received）
        - 窗口的"槽函数"自动被调用（比如 _on_data）
        - 这样数据就自动从数据源流到界面了
        """
        # 数据源发数据 → 窗口的 _on_data 处理
        source.data_received.connect(self._on_data)
        # 数据源发结果 → 窗口的 _on_result 处理
        source.result_received.connect(self._on_result)
        # 数据源发工件 ID → 窗口的 _on_obj_id 处理
        source.obj_id_received.connect(self._on_obj_id)
        # 数据源发模型列表 → 窗口的 _on_model_list 处理
        source.model_list_received.connect(self._on_model_list)
        # 连接状态变化 → 窗口的 _on_connection_changed 处理
        source.connection_changed.connect(self._on_connection_changed)
        # 用户在顶部栏选了模型 → 发送给数据源
        self._header.model_selected.connect(source.send_model)

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
        """处理工件 ID"""
        self._header.set_obj_id(obj_id)

    def _on_model_list(self, models: list):
        """处理模型列表"""
        self._header.set_model_list(models)

    def _on_connection_changed(self, connected: bool):
        """处理连接状态变化"""
        self._status_bar.set_connected(connected)
