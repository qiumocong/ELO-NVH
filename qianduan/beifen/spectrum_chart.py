"""
时频谱图组件（STFT 伪彩图）

作用：显示单个通道的短时傅里叶变换结果。

和旧版频谱图的区别：
- 旧版：FFT → 频率-幅值 一条曲线（静态快照）
- 新版：STFT → 时间×频率→能量 一张热力图（时频分布）

横轴 = 时间（秒），纵轴 = 频率（Hz），颜色 = 能量（幅值）
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
import pyqtgraph as pg
import numpy as np
from config import SAMPLE_RATE
from fft_utils import compute_stft
import traceback


class SpectrumChart(QWidget):
    """单通道时频谱图（STFT 伪彩图）"""

    TITLES = {
        "x": "X 时频谱", "y": "Y 时频谱", "z": "Z 时频谱",
    }

    SIDE_NAMES = {"left": "左", "right": "右"}

    def __init__(self, channel: str, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._first_update = True  # 调试用
        self._setup_ui()

    def _resolve(self):
        """解析 channel 名，返回 (base, display_title)"""
        if "_" in self.channel:
            side, base = self.channel.split("_", 1)
            return base, f"{self.SIDE_NAMES.get(side, side)} {self.TITLES.get(base, base)}"
        return self.channel, self.TITLES.get(self.channel, self.channel)

    def _setup_ui(self):
        base, display_title = self._resolve()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        label = QLabel(display_title)
        label.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(label)

        # pyqtgraph 绘图组件
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel("bottom", "时间", units="s")
        self._plot_widget.setLabel("left", "频率", units="Hz")
        self._plot_widget.setMinimumHeight(120)

        # 坐标轴刻度字体缩小，禁用自动 SI 前缀
        axis_font = pg.QtGui.QFont()
        axis_font.setPointSize(8)
        for ax_name in ('left', 'bottom'):
            axis = self._plot_widget.getAxis(ax_name)
            axis.setStyle(tickFont=axis_font)
            axis.enableAutoSIPrefix(False)
            lf = pg.QtGui.QFont(); lf.setPointSize(8)
            axis.label.setFont(lf)

        # 热力图图层
        self._image_item = pg.ImageItem()
        self._plot_widget.addItem(self._image_item)

        # 颜色映射：黑→蓝→红→黄→白（能量从低到高）
        cmap = pg.ColorMap(
            pos=[0.0, 0.25, 0.5, 0.75, 1.0],
            color=[(0, 0, 0), (0, 0, 180), (200, 0, 0), (255, 200, 0), (255, 255, 255)],
        )
        self._image_item.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))

        layout.addWidget(self._plot_widget)

    def update_from_time_data(self, time_values: list, timestamps: list = None):
        """
        接收时域数据，做 STFT，画时频热力图。

        参数:
            time_values: 最新的时域数据列表
            timestamps: 对应的时间戳列表（可选，用于自动推算采样率）
        """
        if len(time_values) < 64:
            return

        # 根据实际时间戳推算采样率，否则用配置默认值
        sr = SAMPLE_RATE
        if timestamps and len(timestamps) > 1:
            dt = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
            if dt > 0:
                sr = 1.0 / dt

        try:
            times, freqs, magnitudes = compute_stft(
                time_values,
                sample_rate=int(sr),
                window_size=256,
                hop_size=64,
            )

            if magnitudes.size == 0:
                return

            if self._first_update:
                print(f"[频谱] {self.channel}: {len(time_values)}点 → {magnitudes.shape[1]}帧 × {magnitudes.shape[0]}频段")
                self._first_update = False

            mag_db = 20 * np.log10(magnitudes + 1e-10)

            # self._image_item.setLevels([-60, 0])

            t_min = times[0] if len(times) > 0 else 0
            t_max = times[-1] if len(times) > 0 else 1
            if t_max == t_min:
                t_max = t_min + 0.1
            f_min = freqs[0]
            f_max = freqs[-1]
            # self._image_item.setRect(t_min, f_min, t_max - t_min, f_max - f_min)

            # self._image_item.setImage(mag_db.T)
            # self._image_item.setImage(mag_db.T, autoLevels=False)
            self._image_item.setImage(mag_db.T,
                                      levels=(-60, 0),
                                      rect=(t_min, f_min, t_max - t_min, f_max - f_min))
            # except Exception as e:
        #     print(f"[频谱错误] {self.channel}: {e}")
        except Exception:
            132 + print(f"[频谱错误] {self.channel}:")
            133 + traceback.print_exc()

    def clear(self):
        """清空数据"""
        self._image_item.clear()
