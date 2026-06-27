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

    COLORS = {
        "x": "#E74C3C", "y": "#2ECC71", "z": "#3498DB", "current": "#F39C12",
    }

    LABELS = {
        "x": "X 方向振动", "y": "Y 方向振动", "z": "Z 方向振动", "current": "电流",
    }

    UNITS = {
        "x": "m/s²", "y": "m/s²", "z": "m/s²", "current": "A",
    }

    SIDE_NAMES = {"left": "左", "right": "右"}

    def __init__(self, channel: str, parent=None):
        """
        参数:
            channel: 如 "left_x", "right_y", 或单纯的 "x", "y", "current"
        """
        super().__init__(parent)
        self.channel = channel
        maxlen = MAX_POINTS if MAX_POINTS > 0 else None
        self._times = collections.deque(maxlen=maxlen)
        self._values = collections.deque(maxlen=maxlen)
        self._setup_ui()

    def _resolve(self):
        """解析 channel 名，返回 (base, side_name, display_label)"""
        if "_" in self.channel:
            side, base = self.channel.split("_", 1)
            return base, self.SIDE_NAMES.get(side, side), \
                   f"{self.SIDE_NAMES.get(side, side)} {self.LABELS.get(base, base)}"
        return self.channel, "", self.LABELS.get(self.channel, self.channel)

    def _setup_ui(self):
        base, side, display_label = self._resolve()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        label = QLabel(display_label)
        label.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(label)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel("bottom", "时间", units="s")
        y_label = self.LABELS.get(base, base)
        self._plot_widget.setLabel("left", y_label, units=self.UNITS.get(base, ""))
        self._plot_widget.setMinimumHeight(100)

        # 坐标轴刻度字体缩小，禁用自动 SI 前缀（避免 0.7A 显示为 700mA）
        axis_font = pg.QtGui.QFont()
        axis_font.setPointSize(8)
        for ax_name in ('left', 'bottom'):
            axis = self._plot_widget.getAxis(ax_name)
            axis.setStyle(tickFont=axis_font)
            axis.enableAutoSIPrefix(False)
            lf = pg.QtGui.QFont(); lf.setPointSize(8)
            axis.label.setFont(lf)

        color = self.COLORS.get(base, "#333")
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
