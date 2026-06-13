"""
时域曲线图组件

作用：显示单个通道的实时时域曲线。

什么是"时域"？
- 横轴是时间，纵轴是传感器的测量值
- 比如 X 方向振动的时域图，横轴是时间（秒），纵轴是加速度（g）
- 曲线实时滚动，最新的数据在右边，旧数据从左边滚出去

这个组件会被实例化 4 次：
- X 振动（红色）、Y 振动（绿色）、Z 振动（蓝色）、电流（橙色）

数据存储：
- 用 collections.deque 存数据，设置最大长度 MAX_POINTS
- deque 的特性：满了之后自动丢弃最旧的数据（先进先出）
- 这样内存不会无限增长
"""

import collections
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
import pyqtgraph as pg
from config import MAX_POINTS


class TimeChart(QWidget):
    """单通道时域曲线图"""

    # 每个通道的曲线颜色
    COLORS = {
        "x": "#E74C3C",       # 红色
        "y": "#2ECC71",       # 绿色
        "z": "#3498DB",       # 蓝色
        "current": "#F39C12", # 橙色
    }

    # 每个通道的标题文字
    LABELS = {
        "x": "X 方向振动",
        "y": "Y 方向振动",
        "z": "Z 方向振动",
        "current": "电流",
    }

    # 每个通道的纵轴单位
    UNITS = {
        "x": "g",    # 加速度单位
        "y": "g",
        "z": "g",
        "current": "A",  # 电流单位：安培
    }

    def __init__(self, channel: str, parent=None):
        """
        参数:
            channel: 通道名称，必须是 "x", "y", "z", "current" 之一
        """
        super().__init__(parent)
        self.channel = channel

        # 用 deque 存数据，最多保留 MAX_POINTS 个点
        # deque(maxlen=N) 的特性：满了自动丢弃最左边（最旧）的数据
        self._times = collections.deque(maxlen=MAX_POINTS)
        self._values = collections.deque(maxlen=MAX_POINTS)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # 标题标签
        label = QLabel(self.LABELS.get(self.channel, self.channel))
        label.setStyleSheet("font-size: 12px; font-weight: bold; color: #444;")
        layout.addWidget(label)

        # pyqtgraph 绘图组件（高性能实时图表库）
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")           # 白色背景
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)  # 显示网格线
        self._plot_widget.setLabel("bottom", "时间", units="s")  # 横轴标签
        self._plot_widget.setLabel("left", self.LABELS.get(self.channel, ""), units=self.UNITS.get(self.channel, ""))
        self._plot_widget.setMinimumHeight(120)  # 最小高度

        # 创建曲线（设置颜色和线宽）
        color = self.COLORS.get(self.channel, "#333")
        pen = pg.mkPen(color=color, width=1.5)
        self._curve = self._plot_widget.plot(pen=pen)

        layout.addWidget(self._plot_widget)

    def add_data(self, times: list, values: list):
        """
        添加新数据并更新曲线。

        参数:
            times: 时间点列表，比如 [0.001, 0.002, 0.003]
            values: 对应的数值列表，比如 [0.12, 0.15, 0.11]
        """
        self._times.extend(times)
        self._values.extend(values)
        self._update_plot()

    def clear(self):
        """清空所有数据"""
        self._times.clear()
        self._values.clear()
        self._curve.setData([], [])

    def _update_plot(self):
        """把 deque 里的数据画到曲线上"""
        if self._times:
            # setData 会清除旧曲线，画上新数据
            self._curve.setData(list(self._times), list(self._values))
