"""
STFT 短时傅里叶变换工具模块

功能：把时域信号转换成时频分布（spectrogram 伪彩图）。

和普通 FFT 的区别：
- FFT：对整段数据做一次变换，得到"频率→幅值"一条曲线
- STFT：用滑动窗口反复做 FFT，得到"时间×频率→能量"一张热力图

输出的二维矩阵：
- 横轴 = 时间（每一列对应一个时间窗口）
- 纵轴 = 频率（每一行对应一个频率 bin）
- 值 = 该时刻该频率的能量（幅值）
"""

import numpy as np


def compute_stft(
    data: list[float],
    sample_rate: int = 1000,
    window_size: int = 256,
    hop_size: int = 64,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    对时域数据做短时傅里叶变换，返回时频矩阵。

    原理：
    1. 把信号切成重叠的小段（每段 window_size 个点，相邻段间隔 hop_size 个点）
    2. 每段加 Hann 窗后做 FFT
    3. 把所有段的 FFT 结果拼成一个二维矩阵

    参数:
        data: 时域数据（一列数字）
        sample_rate: 采样频率（Hz），默认 1000
        window_size: 每段的长度（点数），越大频率分辨率越高但时间分辨率越低
        hop_size: 相邻两段的间隔（点数），越小时间分辨率越高但计算量越大

    返回:
        (times, freqs, magnitudes)
        - times: 每个时间窗口的中心时间（秒），长度 = 时间帧数
        - freqs: 频率轴（Hz），长度 = window_size//2 + 1
        - magnitudes: 二维数组 shape=(频率数, 时间帧数)，值为能量幅值
    """
    signal = np.array(data, dtype=float)
    n = len(signal)
    if n < window_size:
        signal = np.pad(signal, (0, window_size - n))
        n = window_size

    # Hann 窗
    window = 0.5 * (1 - np.cos(2 * np.pi * np.arange(window_size) / (window_size - 1)))

    # 计算有多少个时间帧
    num_frames = 1 + (n - window_size) // hop_size
    num_freqs = window_size // 2 + 1

    # 时频矩阵
    magnitudes = np.zeros((num_freqs, num_frames))

    for i in range(num_frames):
        start = i * hop_size
        segment = signal[start : start + window_size] * window
        fft_result = np.fft.rfft(segment)
        magnitudes[:, i] = np.abs(fft_result) / window_size * 2

    # 时间轴：每个窗口的中心时刻
    center_offsets = np.arange(num_frames) * hop_size + window_size / 2
    times = center_offsets / sample_rate

    # 频率轴
    freqs = np.fft.rfftfreq(window_size, d=1.0 / sample_rate)

    return times, freqs, magnitudes
