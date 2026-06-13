"""
FFT 计算工具模块

功能：把时域数据（传感器采集的波形）转换成频域数据（频率-幅值谱）

什么是 FFT（快速傅里叶变换）？
- 传感器采集的原始数据是"时域"的：横轴是时间，纵轴是振幅
- FFT 可以把它转换成"频域"：横轴是频率，纵轴是幅值
- 这样能看出振动主要由哪些频率组成，用于故障诊断

举例：如果 X 方向振动的频谱在 50Hz 处有很高的峰，
说明存在 50Hz 的振动，可能是电机转速引起的。
"""

import numpy as np


def hann_window(n: int) -> np.ndarray:
    """
    生成 Hann 窗函数。

    为什么要加窗？
    - 直接对数据做 FFT 会导致"频谱泄漏"（频率分量扩散到相邻频率）
    - 加窗可以减少这种泄漏，让频谱更清晰
    - Hann 窗是最常用的窗函数之一，适合一般场景

    参数:
        n: 窗口长度（数据点数）
    返回:
        长度为 n 的 Hann 窗数组，值在 0~1 之间
    """
    return 0.5 * (1 - np.cos(2 * np.pi * np.arange(n) / (n - 1)))


def compute_fft(data: list[float], sample_rate: int = 1000) -> tuple[np.ndarray, np.ndarray]:
    """
    对时域数据做 FFT，返回频率数组和幅值数组。

    这是"前端计算"模式：前端拿到原始数据后自己算频谱。

    参数:
        data: 时域数据（一列数字，比如 [0.1, 0.2, -0.1, ...]）
        sample_rate: 采样频率（每秒多少个点），默认 1000Hz
    返回:
        (频率数组, 幅值数组)
        - 频率数组：每个频率点的 Hz 值，比如 [0, 1, 2, ..., 500]
        - 幅值数组：对应频率的振动强度
    """
    n = len(data)
    if n == 0:
        return np.array([]), np.array([])

    # 转成 numpy 数组
    signal = np.array(data, dtype=float)

    # 加 Hann 窗，减少频谱泄漏
    window = hann_window(n)
    signal = signal * window

    # 做 FFT（rfft 是针对实数信号的优化版本，只返回正频率部分）
    fft_result = np.fft.rfft(signal)

    # 计算幅值：取绝对值，归一化，乘 2（因为单边谱要把负频率的能量加到正频率）
    magnitude = np.abs(fft_result) / n * 2

    # 计算频率轴：rfftfreq 自动生成对应的频率值
    # d=1.0/sample_rate 表示采样间隔（比如 1000Hz 时，间隔是 0.001 秒）
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    return freqs, magnitude


def compute_fft_from_backend(freqs: list[float], magnitudes: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """
    直接使用后端推送的频谱数据（不做计算，只做格式转换）。

    这是"后端计算"模式：后端已经算好频谱，前端直接展示。
    如果后端支持这种模式，就不需要前端做 FFT 了。

    参数:
        freqs: 后端发来的频率数组
        magnitudes: 后端发来的幅值数组
    返回:
        转成 numpy 数组后的 (频率数组, 幅值数组)
    """
    return np.array(freqs), np.array(magnitudes)
