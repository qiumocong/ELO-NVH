import nidaqmx
import numpy as np
import matplotlib.pyplot as plt
from nidaqmx.constants import AcquisitionType

# ========== 解决matplotlib中文乱码/字体警告 ==========
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False
# ====================================================

# ====================== 配置参数 ======================
sample_rate = 5000
collect_total_time = 10000.0    # 总采集时长
chunk_samples = 1000        # 每一次读取点数，控制刷新速度
total_chunks = int((sample_rate * collect_total_time) / chunk_samples)

ch_9234 = "cDAQ1Mod1/ai0:3"
ch_9239 = "cDAQ1Mod2/ai0:3"

range_9234 = (-5.0, 5.0)
range_9239 = (-10.0, 10.0)
# ======================================================

# 初始化绘图
plt.ion()
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
lines_9234 = []
lines_9239 = []

# 预先创建曲线对象
for i in range(4):
    l, = ax1.plot([], [], label=f"9234_ai{i}")
    lines_9234.append(l)
for i in range(4):
    l, = ax2.plot([], [], label=f"9239_ai{i}")
    lines_9239.append(l)

ax1.set_title("NI 9234 实时电压")
ax1.set_ylabel("电压(V)")
ax1.legend(loc="upper right")
ax1.grid(True)
ax1.set_ylim(range_9234[0]-0.5, range_9234[1]+0.5)

ax2.set_title("NI 9239 实时电压")
ax2.set_xlabel("时间(s)")
ax2.set_ylabel("电压(V)")
ax2.legend(loc="upper right")
ax2.grid(True)
ax2.set_ylim(range_9239[0]-1, range_9239[1]+1)

# 缓存完整数据，最后保存CSV
full_t = np.array([])
full_9234 = np.empty((4, 0))
full_9239 = np.empty((4, 0))

task_9234 = nidaqmx.Task()
task_9239 = nidaqmx.Task()

try:
    # 9234配置连续采集
    task_9234.ai_channels.add_ai_voltage_chan(
        physical_channel=ch_9234,
        min_val=range_9234[0],
        max_val=range_9234[1]
    )
    task_9234.timing.cfg_samp_clk_timing(
        rate=sample_rate,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=chunk_samples
    )

    # 9239配置连续采集
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

    task_9234.start()
    task_9239.start()

    print(f"开始实时采集，总时长 {collect_total_time}s，分 {total_chunks} 帧刷新")
    t_start = 0.0

    for _ in range(total_chunks):
        # 读取一帧数据
        data_chunk_9234 = np.array(task_9234.read(chunk_samples))
        data_chunk_9239 = np.array(task_9239.read(chunk_samples))

        # 生成当前块时间轴
        t_chunk = np.linspace(t_start, t_start + chunk_samples/sample_rate, chunk_samples, endpoint=False)
        t_start += chunk_samples / sample_rate

        # 拼接进完整数据
        full_t = np.concatenate([full_t, t_chunk])
        full_9234 = np.hstack([full_9234, data_chunk_9234])
        full_9239 = np.hstack([full_9239, data_chunk_9239])

        # 更新每条曲线y数据
        for i in range(4):
            lines_9234[i].set_data(full_t, full_9234[i, :])
            lines_9239[i].set_data(full_t, full_9239[i, :])

        # 自动缩放X轴
        ax1.relim()
        ax1.autoscale_view()
        ax2.relim()
        ax2.autoscale_view()

        fig.canvas.draw()
        fig.canvas.flush_events()

    print("采集全部完成，开始保存CSV...")

finally:
    task_9234.close()
    task_9239.close()
    plt.ioff()
    plt.show()

# 保存完整数据CSV
save_mat = np.column_stack([full_t, full_9234.T, full_9239.T])
header = [
    "时间(s)",
    "9234_ai0(V)","9234_ai1(V)","9234_ai2(V)","9234_ai3(V)",
    "9239_ai0(V)","9239_ai1(V)","9239_ai2(V)","9239_ai3(V)"
]
np.savetxt(
    "daq_stream_data.csv",
    save_mat,
    delimiter=",",
    header=",".join(header),
    comments="",
    fmt="%.6f"
)
print("数据已保存至 daq_stream_data.csv")