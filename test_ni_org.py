import nidaqmx
import numpy as np
import matplotlib.pyplot as plt
import os
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.stream_readers import AnalogMultiChannelReader

# ========== 解决matplotlib中文乱码/字体警告 ==========
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False
# ====================================================

# ====================== 配置参数 ======================
sample_rate = 4800
collect_total_time = 10000.0  # 总采集时长 (s)
chunk_samples = 1000  # 每一次读取点数，控制刷新速度
total_chunks = int((sample_rate * collect_total_time) / chunk_samples)
total_samples = int(sample_rate * collect_total_time)

# 输出路径配置
save_dir = "C:/Users/Noko/PycharmProjects/yanpu/data"
os.makedirs(save_dir, exist_ok=True)
save_file_path = os.path.join(save_dir, "daq_stream_data.csv")
# ======================================================

# ================== 初始化全局大数组 ==================
full_t = np.linspace(0, collect_total_time, total_samples, endpoint=False)
full_9234 = np.zeros((3, total_samples), dtype=np.float64)  # 3通道
full_9234_1 = np.zeros((3, total_samples), dtype=np.float64)  # 3通道
full_9239 = np.zeros((4, total_samples), dtype=np.float64)  # 4通道
# ======================================================

# 初始化绘图
plt.ion()
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
lines_9234 = []
lines_9234_1 = []
lines_9239 = []

for i in range(3):
    l, = ax1.plot([], [], label=f"9234_ai{i}")
    lines_9234.append(l)
for i in range(3):
    l, = ax2.plot([], [], label=f"9234_1_ai{i}")
    lines_9234_1.append(l)
for i in range(4):
    l, = ax3.plot([], [], label=f"9239_ai{i}")
    lines_9239.append(l)

range_9234_accel = (-50.0, 50.0)
range_9239 = (-10.0, 10.0)

ax1.set_title("NI 9234 实时加速度 (3通道)")
ax1.set_ylabel("加速度 (m/s^2)")
ax1.legend(loc="upper right")
ax1.grid(True)
ax1.set_ylim(range_9234_accel[0], range_9234_accel[1])

ax2.set_title("NI 9234-1 实时加速度 (3通道)")
ax2.set_ylabel("加速度 (m/s^2)")
ax2.legend(loc="upper right")
ax2.grid(True)
ax2.set_ylim(range_9234_accel[0], range_9234_accel[1])

ax3.set_title("NI 9239 实时电压 (4通道)")
ax3.set_xlabel("时间 (s)")
ax3.set_ylabel("电压 (V)")
ax3.legend(loc="upper right")
ax3.grid(True)
ax3.set_ylim(range_9239[0] - 1, range_9239[1] + 1)

# 创建一个任务包含所有通道
task = nidaqmx.Task()

try:
    # 第一个9234模块 (3通道加速度计)
    task.ai_channels.add_ai_accel_chan(
        physical_channel="cDAQ1Mod1/ai0:2",
        min_val=range_9234_accel[0],
        max_val=range_9234_accel[1],
        sensitivity=100,
        sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
        current_excit_source=ExcitationSource.INTERNAL,
        current_excit_val=0.002,
        units=AccelUnits.METERS_PER_SECOND_SQUARED
    )

    # 第二个9234模块 (3通道加速度计)
    task.ai_channels.add_ai_accel_chan(
        physical_channel="cDAQ1Mod2/ai0:2",
        min_val=range_9234_accel[0],
        max_val=range_9234_accel[1],
        sensitivity=100,
        sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
        current_excit_source=ExcitationSource.INTERNAL,
        current_excit_val=0.002,
        units=AccelUnits.METERS_PER_SECOND_SQUARED
    )

    # 9239模块 (4通道电压)
    task.ai_channels.add_ai_voltage_chan(
        physical_channel="cDAQ1Mod3/ai0:3",
        min_val=range_9239[0],
        max_val=range_9239[1]
    )

    # 配置采样时钟 - 增加缓冲区大小
    task.timing.cfg_samp_clk_timing(
        rate=sample_rate,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=chunk_samples * 2  # 缓冲区设为2倍
    )

    # 额外设置更大的缓冲区
    task.in_stream.input_buf_size = 1000000  # 设置缓冲区大小为1,000,000样本

    # 绑定高性能 Stream Reader
    reader = AnalogMultiChannelReader(task.in_stream)

    # 循环内专用的零拷贝缓冲块 (总共10通道：3+3+4)
    buffer_all = np.zeros((10, chunk_samples), dtype=np.float64)

    task.start()

    print(f"开始实时采集，总时长 {collect_total_time}s，分 {total_chunks} 帧刷新")
    print(f"总通道数：10 (第一个9234: 3通道, 第二个9234: 3通道, 9239: 4通道)")

    # 用于显示进度的变量
    last_progress = 0

    for chunk_idx in range(total_chunks):
        # 1. 读取所有通道数据 - 增加超时时间
        try:
            reader.read_many_sample(
                buffer_all,
                number_of_samples_per_channel=chunk_samples,
                timeout=20.0  # 增加超时时间
            )
        except nidaqmx.errors.DaqReadError as e:
            print(f"读取错误 (chunk {chunk_idx}): {e}")
            # 如果读取失败，尝试清空缓冲区继续
            try:
                task.stop()
                task.start()
                reader.read_many_sample(buffer_all, number_of_samples_per_channel=chunk_samples, timeout=20.0)
            except:
                print("无法恢复采集，退出...")
                break

        # 2. 将数据分离到各个设备的数组中
        start_idx = chunk_idx * chunk_samples
        end_idx = start_idx + chunk_samples

        # 前3个通道是第一个9234
        full_9234[:, start_idx:end_idx] = buffer_all[0:3, :]
        # 中间3个通道是第二个9234
        full_9234_1[:, start_idx:end_idx] = buffer_all[3:6, :]
        # 最后4个通道是9239
        full_9239[:, start_idx:end_idx] = buffer_all[6:10, :]

        # 3. 仅提取用于绘图的最新切片时间轴
        t_plot = full_t[:end_idx]

        # 4. 更新每条曲线 y 数据
        for i in range(3):
            lines_9234[i].set_data(t_plot, full_9234[i, :end_idx])
            lines_9234_1[i].set_data(t_plot, full_9234_1[i, :end_idx])
        for i in range(4):
            lines_9239[i].set_data(t_plot, full_9239[i, :end_idx])

        # 自动缩放X轴 (Y轴前面已锁定范围，避免抖动)
        ax1.relim()
        ax1.autoscale_view(scaley=False)
        ax2.relim()
        ax2.autoscale_view(scaley=False)
        ax3.relim()
        ax3.autoscale_view(scaley=False)

        fig.canvas.draw()
        fig.canvas.flush_events()

        # 显示进度
        progress = (chunk_idx + 1) / total_chunks * 100
        if progress - last_progress >= 0.5:  # 每0.5%显示一次
            print(f"采集进度: {progress:.1f}%")
            last_progress = progress

    print("采集全部完成，开始保存 CSV...")

except KeyboardInterrupt:
    print("\n用户中断采集")
except Exception as e:
    print(f"发生错误: {e}")
finally:
    task.close()
    plt.ioff()
    plt.show()

# 保存完整数据 CSV
print(f"正在写入大文件，请稍候...")
save_mat = np.column_stack([full_t, full_9234.T, full_9234_1.T, full_9239.T])
header = [
    "时间(s)",
    "9234_ai0(m/s^2)", "9234_ai1(m/s^2)", "9234_ai2(m/s^2)",
    "9234_1_ai0(m/s^2)", "9234_1_ai1(m/s^2)", "9234_1_ai2(m/s^2)",
    "9239_ai0(V)", "9239_ai1(V)", "9239_ai2(V)", "9239_ai3(V)"
]

np.savetxt(
    save_file_path,
    save_mat,
    delimiter=",",
    header=",".join(header),
    comments="",
    fmt="%.6f"
)
print(f"数据已安全保存至 {save_file_path}")
print(f"总数据点：{total_samples}，总通道数：10 (3+3+4)")