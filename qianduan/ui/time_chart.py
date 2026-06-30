"""
时域曲线图组件 — 用 list 存储，显示时自动降采样
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
import pyqtgraph as pg
import numpy as np
from config import MAX_POINTS

# 显示时最多绘制的点数，超过则降采样
MAX_DISPLAY_PTS = 3000


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
        super().__init__(parent)
        self.channel = channel
        self._times = []      # list, 支持 O(1) 索引和切片
        self._values = []
        self._maxlen = MAX_POINTS if MAX_POINTS > 0 else None
        self._setup_ui()

    def _resolve(self):
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
        self._curve.setDownsampling(auto=True, method='subsample')
        self._curve.setClipToView(True)

        layout.addWidget(self._plot_widget)

    def add_data(self, times: list, values: list):
        self._times.extend(times)
        self._values.extend(values)
        if self._maxlen and len(self._times) > self._maxlen:
            drop = len(self._times) - self._maxlen
            self._times = self._times[drop:]
            self._values = self._values[drop:]
        self._update_plot()

    def clear(self):
        self._times.clear()
        self._values.clear()
        self._curve.setData([], [])

    def _update_plot(self):
        if not self._times:
            return
        n = len(self._times)
        step = max(1, n // MAX_DISPLAY_PTS)
        if step == 1:
            self._curve.setData(np.array(self._times), np.array(self._values))
        else:
            # 等间隔降采样，用 O(1) 索引直接切片
            self._curve.setData(
                np.array(self._times[::step]),
                np.array(self._values[::step]),
            )
