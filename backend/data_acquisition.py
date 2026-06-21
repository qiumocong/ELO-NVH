import nidaqmx
import numpy as np
import matplotlib.pyplot as plt
from nidaqmx.constants import AcquisitionType
import threading
import time
from collections import deque

class DataAcquisition:
    def __init__(self, config):
        self.config = config
        self.sample_rate = config["SAMPLE_RATE"]
        self.chunk_samples = config["CHUNK_SAMPLES"]
        self.ch_9234 = config["CH_9234"]
        self.ch_9239 = config["CH_9239"]
        self.range_9234 = config["RANGE_9234"]
        self.range_9239 = config["RANGE_9239"]
        self.input_indices = config["INPUT_CHANNEL_INDICES"]

        self.task_9234 = None
        self.task_9239 = None
        self.is_running = False
        self.thread = None

        # 数据缓存（用于实时绘图和最终保存）
        self.full_t = np.array([])
        self.full_data = np.empty((8, 0))   # 8 通道

        # 绘图相关
        self.fig = None
        self.axes = None
        self.lines = None
        self.plot_enabled = config.get("PLOT_ENABLE", False)

    def start(self):
        """启动采集线程"""
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._acquisition_loop, daemon=True)
        self.thread.start()

        # 初始化绘图（主线程中创建）
        if self.plot_enabled:
            self._init_plot()

    def stop(self):
        """停止采集，返回全部数据 (t, data_8ch)"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        # 关闭任务
        if self.task_9234:
            self.task_9234.close()
        if self.task_9239:
            self.task_9239.close()
        if self.plot_enabled:
            plt.ioff()
            plt.show(block=False)
        return self.full_t.copy(), self.full_data.copy()

    def _acquisition_loop(self):
        # 创建任务
        self.task_9234 = nidaqmx.Task()
        self.task_9239 = nidaqmx.Task()

        self.task_9234.ai_channels.add_ai_voltage_chan(
            self.ch_9234, min_val=self.range_9234[0], max_val=self.range_9234[1]
        )
        self.task_9234.timing.cfg_samp_clk_timing(
            self.sample_rate, sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=self.chunk_samples
        )

        self.task_9239.ai_channels.add_ai_voltage_chan(
            self.ch_9239, min_val=self.range_9239[0], max_val=self.range_9239[1]
        )
        self.task_9239.timing.cfg_samp_clk_timing(
            self.sample_rate, sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=self.chunk_samples
        )

        self.task_9234.start()
        self.task_9239.start()

        t_start = 0.0
        while self.is_running:
            try:
                data4_9234 = np.array(self.task_9234.read(self.chunk_samples))
                data4_9239 = np.array(self.task_9239.read(self.chunk_samples))
            except Exception as e:
                print(f"[采集] 读取错误: {e}")
                break

            # 合并为 8 通道 [通道数, 样本数]
            data_chunk = np.vstack([data4_9234, data4_9239])

            # 时间轴
            t_chunk = np.linspace(t_start, t_start + self.chunk_samples/self.sample_rate,
                                  self.chunk_samples, endpoint=False)
            t_start += self.chunk_samples / self.sample_rate

            # 追加到缓存
            self.full_t = np.concatenate([self.full_t, t_chunk])
            self.full_data = np.hstack([self.full_data, data_chunk])

            # 实时绘图
            if self.plot_enabled:
                self._update_plot(t_chunk, data_chunk)

        # 循环结束，关闭任务
        if self.task_9234:
            self.task_9234.stop()
            self.task_9234.close()
        if self.task_9239:
            self.task_9239.stop()
            self.task_9239.close()

    def _init_plot(self):
        plt.ion()
        self.fig, self.axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        self.lines = []
        # 显示全部 8 通道
        for i in range(4):
            l, = self.axes[0].plot([], [], label=f"9234_ai{i}")
            self.lines.append(l)
        for i in range(4):
            l, = self.axes[1].plot([], [], label=f"9239_ai{i}")
            self.lines.append(l)
        self.axes[0].set_title("NI 9234")
        self.axes[0].legend(loc="upper right")
        self.axes[1].set_title("NI 9239")
        self.axes[1].set_xlabel("时间 (s)")
        self.axes[1].legend(loc="upper right")
        plt.tight_layout()

    def _update_plot(self, t_chunk, data_chunk):
        # 更新全部曲线
        for i in range(8):
            self.lines[i].set_data(self.full_t, self.full_data[i, :])
        # 自适应坐标轴
        for ax in self.axes:
            ax.relim()
            ax.autoscale_view()
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()