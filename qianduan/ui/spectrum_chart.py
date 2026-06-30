"""
时频谱图组件（增量 STFT 伪彩图）

横轴 = 时间（秒），纵轴 = 频率（Hz），颜色 = 能量（dB）
采用增量 STFT：每次只对新数据做变换，追加到已有频谱后面
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
import pyqtgraph as pg
import numpy as np
import traceback
from config import SAMPLE_RATE
from fft_utils import compute_stft


class SpectrumChart(QWidget):
    """单通道时频谱图（增量 STFT 伪彩图）"""

    TITLES = {"x": "X 时频谱", "y": "Y 时频谱", "z": "Z 时频谱"}
    SIDE_NAMES = {"left": "左", "right": "右"}

    WINDOW_SIZE = 256
    HOP_SIZE = 64

    def __init__(self, channel: str, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._first_update = True
        # 增量状态
        self._processed_count = 0       # 已处理的数据点数
        self._sr = SAMPLE_RATE          # 有效采样率
        self._acc_times = np.array([])  # 累积的时间帧
        self._acc_freqs = np.array([])  # 频率轴（固定）
        self._acc_mag_db = None         # 累积的 dB 矩阵 (num_freqs, total_frames)
        self._setup_ui()

    def _resolve(self):
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

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel("bottom", "时间", units="s")
        self._plot_widget.setLabel("left", "频率", units="Hz")
        self._plot_widget.setMinimumHeight(120)

        axis_font = pg.QtGui.QFont()
        axis_font.setPointSize(8)
        for ax_name in ('left', 'bottom'):
            axis = self._plot_widget.getAxis(ax_name)
            axis.setStyle(tickFont=axis_font)
            axis.enableAutoSIPrefix(False)
            lf = pg.QtGui.QFont(); lf.setPointSize(8)
            axis.label.setFont(lf)

        self._image_item = pg.ImageItem()
        self._plot_widget.addItem(self._image_item)

        cmap = pg.ColorMap(
            pos=[0.0, 0.25, 0.5, 0.75, 1.0],
            color=[(0, 0, 0), (0, 0, 180), (200, 0, 0), (255, 200, 0), (255, 255, 255)],
        )
        self._image_item.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))

        layout.addWidget(self._plot_widget)

    def update_from_time_data(self, time_values, timestamps=None):
        """
        增量 STFT：只对新到达的数据做变换，追加到累积频谱。
        time_values / timestamps: list 或 numpy array
        """
        if len(time_values) < self.WINDOW_SIZE:
            return

        # 推算有效采样率
        if timestamps is not None and len(timestamps) > 1:
            dt = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)
            if dt > 0:
                self._sr = 1.0 / dt

        new_start = self._processed_count
        total_len = len(time_values)
        if new_start >= total_len:
            return

        try:
            # 取新数据做 STFT
            new_data = time_values[new_start:]
            n_new = len(new_data)
            if n_new < self.WINDOW_SIZE:
                return

            new_times, new_freqs, new_mag = compute_stft(
                new_data,
                sample_rate=int(self._sr),
                window_size=self.WINDOW_SIZE,
                hop_size=self.HOP_SIZE,
            )

            if new_mag.size == 0:
                return

            # 时间偏移 = 新数据起点在原始时间轴上的位置
            time_offset = new_start / self._sr
            new_times = new_times + time_offset

            new_mag_db = 20 * np.log10(new_mag + 1e-10)

            if self._first_update:
                print(f"[频谱] {self.channel}: 初始 {len(time_values)}点 → {new_mag.shape[1]}帧")
                self._first_update = False

            # 追加到累积结果
            if self._acc_mag_db is None:
                self._acc_times = new_times
                self._acc_freqs = new_freqs
                self._acc_mag_db = new_mag_db
            else:
                self._acc_times = np.concatenate([self._acc_times, new_times])
                self._acc_mag_db = np.hstack([self._acc_mag_db, new_mag_db])

            # 清理旧累积帧（与 MAX_POINTS 对应，但频谱帧更少，不做也行）
            # 记录已处理的数据点
            self._processed_count = total_len

            # 更新图像
            t_min = self._acc_times[0]
            t_max = self._acc_times[-1]
            if t_max <= t_min:
                t_max = t_min + 0.1
            f_min = self._acc_freqs[0]
            f_max = self._acc_freqs[-1]

            self._image_item.setImage(self._acc_mag_db.T,
                                      levels=(-60, 0),
                                      rect=(t_min, f_min, t_max - t_min, f_max - f_min))
        except Exception:
            print(f"[频谱错误] {self.channel}:")
            traceback.print_exc()

    def clear(self):
        self._image_item.clear()
        self._processed_count = 0
        self._acc_times = np.array([])
        self._acc_mag_db = None
