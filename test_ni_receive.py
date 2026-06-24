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
collect_total_time = 10000.0    # 总采集时长 (s)
chunk_samples = 1000            # 每一次读取点数，控制刷新速度
total_chunks = int((sample_rate * collect_total_time) / chunk_samples)
total_samples = int(sample_rate * collect_total_time)

ch_9234 = "cDAQ1Mod1/ai0:3"     # 4通道加速度计
ch_9239 = "cDAQ1Mod2/ai0:3"     # 4通道电压

range_9234_accel = (-490.0, 490.0)
range_9239 = (-10.0, 10.0)         # 电压量程 V

# 输出路径配置
save_dir = "/home/qmc/rmrobot/src/rmrobot/pick_master/scripts/data"
os.makedirs(save_dir, exist_ok=True)
save_file_path = os.path.join(save_dir, "daq_stream_data.csv")
# ======================================================

# ================== 初始化全局大数组 ==================
# 预先分配好所有所需的内存，避免循环中使用 hstack 导致内存爆炸
full_t = np.linspace(0, collect_total_time, total_samples, endpoint=False)
full_9234 = np.zeros((4, total_samples), dtype=np.float64)
full_9239 = np.zeros((4, total_samples), dtype=np.float64)
# ======================================================

# 初始化绘图
plt.ion()
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
lines_9234 = []
lines_9239 = []

for i in range(4):
    l, = ax1.plot([], [], label=f"9234_ai{i}")
    lines_9234.append(l)
for i in range(4):
    l, = ax2.plot([], [], label=f"9239_ai{i}")
    lines_9239.append(l)

ax1.set_title("NI 9234 实时加速度")
ax1.set_ylabel("加速度 (m/s^2)")
ax1.legend(loc="upper right")
ax1.grid(True)
ax1.set_ylim(range_9234_accel[0], range_9234_accel[1])

ax2.set_title("NI 9239 实时电压")
ax2.set_xlabel("时间 (s)")
ax2.set_ylabel("电压 (V)")
ax2.legend(loc="upper right")
ax2.grid(True)
ax2.set_ylim(range_9239[0]-1, range_9239[1]+1)

task_9234 = nidaqmx.Task()
task_9239 = nidaqmx.Task()

try:
    # --- 9234 配置为高精度 IEPE 加速度通道 ---
    task_9234.ai_channels.add_ai_accel_chan(
        physical_channel=ch_9234,
        min_val=range_9234_accel[0],
        max_val=range_9234_accel[1],
        sensitivity=99.8,
        sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
        current_excit_source=ExcitationSource.INTERNAL,
        current_excit_val=0.002,                                  # 开启 2mA 恒流源供电
        units=AccelUnits.METERS_PER_SECOND_SQUARED                # 输出物理量单位
    )
    task_9234.timing.cfg_samp_clk_timing(
        rate=sample_rate,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=chunk_samples
    )

    # --- 9239 配置为常规电压通道 ---
    task_9239.ai_channels.add_ai_voltage_chan(
        physical_channel=ch_9239,
        min_val=range_9239[0],
        max_val=range_9239[1]
    )
    task_9239.timing.cfg_samp_clk_timing(
        rate=sample_rate,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=chunk_samples
    )

    # 绑定高性能 Stream Reader
    reader_9234 = AnalogMultiChannelReader(task_9234.in_stream)
    reader_9239 = AnalogMultiChannelReader(task_9239.in_stream)

    # 循环内专用的零拷贝缓冲块
    buffer_9234 = np.zeros((4, chunk_samples), dtype=np.float64)
    buffer_9239 = np.zeros((4, chunk_samples), dtype=np.float64)

    task_9234.start()
    task_9239.start()

    print(f"开始实时采集，总时长 {collect_total_time}s，分 {total_chunks} 帧刷新")

    for chunk_idx in range(total_chunks):
        # 1. 直接读取数据到缓冲块
        reader_9234.read_many_sample(buffer_9234, number_of_samples_per_channel=chunk_samples, timeout=10.0)
        reader_9239.read_many_sample(buffer_9239, number_of_samples_per_channel=chunk_samples, timeout=10.0)

        # 2. 将缓冲块数据映射到全局数组中（切片赋值，极快且无额外内存开销）
        start_idx = chunk_idx * chunk_samples
        end_idx = start_idx + chunk_samples
        full_9234[:, start_idx:end_idx] = buffer_9234
        full_9239[:, start_idx:end_idx] = buffer_9239

        # 3. 仅提取用于绘图的最新切片时间轴
        t_plot = full_t[:end_idx]

        # 4. 更新每条曲线 y 数据
        for i in range(4):
            lines_9234[i].set_data(t_plot, full_9234[i, :end_idx])
            lines_9239[i].set_data(t_plot, full_9239[i, :end_idx])

        # 自动缩放X轴 (Y轴前面已锁定范围，避免抖动)
        ax1.relim()
        ax1.autoscale_view(scaley=False)
        ax2.relim()
        ax2.autoscale_view(scaley=False)

        fig.canvas.draw()
        fig.canvas.flush_events()

    print("采集全部完成，开始保存 CSV...")

finally:
    task_9234.close()
    task_9239.close()
    plt.ioff()
    plt.show()

# 保存完整数据 CSV (注意转置以匹配时间列)
print(f"正在写入大文件，请稍候...")
save_mat = np.column_stack([full_t, full_9234.T, full_9239.T])
header = [
    "时间(s)",
    "9234_ai0(m/s^2)","9234_ai1(m/s^2)","9234_ai2(m/s^2)","9234_ai3(m/s^2)",
    "9239_ai0(V)","9239_ai1(V)","9239_ai2(V)","9239_ai3(V)"
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