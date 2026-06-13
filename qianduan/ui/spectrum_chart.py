"""
频谱图组件

作用：显示单个通道的 FFT 频谱。

什么是"频谱图"？
- 横轴是频率（Hz），纵轴是幅值
- 能看出振动主要由哪些频率组成
- 比如在 50Hz 处有高峰，说明存在 50Hz 的振动

这个组件会被实例化 3 次：
- X 频谱（红色）、Y 频谱（绿色）、Z 频谱（蓝色）
- 电流不需要做频谱分析

频谱数据来源有两种：
1. 前端计算：用 fft_utils.compute_fft() 对时域数据做 FFT（默认方式）
2. 后端推送：后端直接发频谱数据过来，前端只负责展示
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
import pyqtgraph as pg
import numpy as np
from config import SAMPLE_RATE, FFT_WINDOW_SIZE
from fft_utils import compute_fft, compute_fft_from_backend


class SpectrumChart(QWidget):
    """单通道频谱图"""

    # 每个通道的颜色
    COLORS = {
        "x": "#E74C3C",  # 红色
        "y": "#2ECC71",  # 绿色
        "z": "#3498DB",  # 蓝色
    }

    # 每个通道的标题
    LABELS = {
        "x": "X 频谱",
        "y": "Y 频谱",
        "z": "Z 频谱",
    }

    def __init__(self, channel: str, parent=None):
        """
        参数:
            channel: 通道名称，必须是 "x", "y", "z" 之一
        """
        super().__init__(parent)
        self.channel = channel
        self._time_data = []  # 存储时域数据（用于前端 FFT 计算）
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # 标题
        label = QLabel(self.LABELS.get(self.channel, self.channel))
        label.setStyleSheet("font-size: 12px; font-weight: bold; color: #444;")
        layout.addWidget(label)

        # pyqtgraph 绘图组件
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel("bottom", "频率", units="Hz")  # 横轴：频率
        self._plot_widget.setLabel("left", "幅值")                 # 纵轴：幅值
        self._plot_widget.setMinimumHeight(120)

        # 创建曲线
        color = self.COLORS.get(self.channel, "#333")
        pen = pg.mkPen(color=color, width=1.5)
        self._curve = self._plot_widget.plot(pen=pen)

        layout.addWidget(self._plot_widget)

    def update_from_time_data(self, time_values: list):
        """
        方式一：前端计算频谱（默认方式）。
        接收时域数据，自己做 FFT，然后画频谱图。

        参数:
            time_values: 最新的时域数据列表
        """
        if len(time_values) < 16:  # 数据太少没意义
            return
        # 取最近 FFT_WINDOW_SIZE 个点做 FFT
        recent = time_values[-FFT_WINDOW_SIZE:]
        freqs, magnitudes = compute_fft(recent, SAMPLE_RATE)
        self._plot(freqs, magnitudes)

    def update_from_backend(self, freqs: list, magnitudes: list):
        """
        方式二：使用后端推送的频谱数据（不做计算，直接画）。
        如果后端已经算好了频谱，前端直接展示即可。

        参数:
            freqs: 频率数组
            magnitudes: 幅值数组
        """
        f, m = compute_fft_from_backend(freqs, magnitudes)
        self._plot(f, m)

    def _plot(self, freqs: np.ndarray, magnitudes: np.ndarray):
        """画频谱曲线"""
        if len(freqs) > 0:
            self._curve.setData(freqs, magnitudes)

    def clear(self):
        """清空数据"""
        self._time_data.clear()
        self._curve.setData([], [])
