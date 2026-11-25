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
        # 原始极值独立保存，不受显示缩放、降采样和历史曲线裁剪影响。
        self._track_extrema = self._resolve()[0] in ("x", "y", "z")
        self._raw_min = None
        self._raw_max = None
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

        if self._track_extrema:
            self._extrema_label = QLabel()
            self._extrema_label.setStyleSheet("font-size: 12px; color: #555;")
            self._extrema_label.setWordWrap(True)
            self._extrema_label.setToolTip(
                "统计本轮前端收到的原始加速度，保留正负号；不受显示缩放影响。"
                "采集结束后保留，清空本工位曲线时重置。"
            )
            self._update_extrema_label()
            layout.addWidget(self._extrema_label)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        axis_label_style = {"color": "#000000", "font-size": "10pt"}
        self._plot_widget.setLabel("bottom", "时间", units="s", **axis_label_style)
        y_label = self.LABELS.get(base, base)
        self._plot_widget.setLabel("left", y_label, units=self.UNITS.get(base, ""), **axis_label_style)
        self._plot_widget.setMinimumHeight(100)

        axis_font = pg.QtGui.QFont()
        axis_font.setPointSize(10)
        for ax_name in ('left', 'bottom'):
            axis = self._plot_widget.getAxis(ax_name)
            # 白底上明确使用黑色轴线、刻度和数字，避免默认灰色可读性不足。
            axis.setPen(pg.mkPen("#000000", width=1))
            axis.setTickPen(pg.mkPen("#000000", width=1))
            axis.setTextPen(pg.mkPen("#000000"))
            axis.setStyle(tickFont=axis_font)
            axis.enableAutoSIPrefix(False)
            axis.label.setFont(axis_font)

        color = self.COLORS.get(base, "#333")
        pen = pg.mkPen(color=color, width=1.5)
        self._curve = self._plot_widget.plot(pen=pen)
        self._curve.setDownsampling(auto=True, method='subsample')
        self._curve.setClipToView(True)

        layout.addWidget(self._plot_widget)

    def add_data(self, times: list, values: list, raw_values=None):
        """values 用于绘图；raw_values 是缩放前数据，省略时沿用 values。"""
        if self._track_extrema:
            # 先统计完整新增批次，再裁剪/降采样，避免漏掉早期或瞬时峰值。
            raw = np.asarray(values if raw_values is None else raw_values, dtype=np.float64)
            finite = raw[np.isfinite(raw)]
            if finite.size:
                batch_min, batch_max = float(finite.min()), float(finite.max())
                self._raw_min = batch_min if self._raw_min is None else min(self._raw_min, batch_min)
                self._raw_max = batch_max if self._raw_max is None else max(self._raw_max, batch_max)
                self._update_extrema_label()
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
        self._raw_min = None
        self._raw_max = None
        if self._track_extrema:
            self._update_extrema_label()

    def _update_extrema_label(self):
        maximum = "——" if self._raw_max is None else f"{self._raw_max:.3f}"
        minimum = "——" if self._raw_min is None else f"{self._raw_min:.3f}"
        # 仅突出极值数字，说明文字沿用原字号，便于快速读取各轴峰值。
        number_style = "font-size: 16px; font-weight: bold; color: #000000;"
        self._extrema_label.setText(
            "本轮原始极值（m/s²）<br>"
            f'最大：<span style="{number_style}">{maximum}</span>&nbsp;&nbsp;'
            f'最小：<span style="{number_style}">{minimum}</span>'
        )

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
