import nidaqmx
import numpy as np
import matplotlib.pyplot as plt
from nidaqmx.constants import AcquisitionType
import time

# ==================== 全局配置（防溢出核心参数）====================
SAMPLE_RATE = 5000          # 采样率
READ_SAMPLES = 500          # 单次读取点数(更小=读取更频繁)
DAQ_BUFFER = 50000          # DAQ硬件缓冲区(拉满)
PLOT_INTERVAL = 5           # 每5轮采集才刷新一次图像(大幅降CPU)
VIEW_SEC = 3.0              # 画面显示最近3秒数据
VIEW_POINTS = int(SAMPLE_RATE * VIEW_SEC)

# DAQ通道与量程
CH_9234 = "cDAQ1Mod1/ai0:3"
CH_9239 = "cDAQ1Mod2/ai0:3"
RANGE_9234 = (-5.0, 5.0)
RANGE_9239 = (-10.0, 10.0)
# ===================================================================

# 中文显示
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

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

ax1.set_title("NI 9234 实时电压")
ax1.set_ylabel("电压(V)")
ax1.legend(loc="upper right")
ax1.grid(True)
ax1.set_ylim(RANGE_9234[0]-0.5, RANGE_9234[1]+0.5)

ax2.set_title("NI 9239 实时电压")
ax2.set_xlabel("时间(s)")
ax2.set_ylabel("电压(V)")
ax2.legend(loc="upper right")
ax2.grid(True)
ax2.set_ylim(RANGE_9239[0]-1, RANGE_9239[1]+1)

# --------------- 绘图滚动缓冲区（仅用于画面显示）---------------
t_buf = np.array([], dtype=np.float64)
data_9234_view = np.empty((4, 0), dtype=np.float64)
data_9239_view = np.empty((4, 0), dtype=np.float64)

# --------------- 全量数据缓冲区（最终用来保存CSV）---------------
full_t = np.array([], dtype=np.float64)
full_9234 = np.empty((4, 0), dtype=np.float64)
full_9239 = np.empty((4, 0), dtype=np.float64)

t_now = 0.0
plot_cnt = 0  # 绘图计数器

# DAQ任务
task1 = nidaqmx.Task()
task2 = nidaqmx.Task()

try:
    # 配置 9234
    task1.ai_channels.add_ai_accel_chan(
        physical_channel=CH_9234,
        min_val=RANGE_9234[0],
        max_val=RANGE_9234[1]
    )
    task1.timing.cfg_samp_clk_timing(
        rate=SAMPLE_RATE,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=DAQ_BUFFER
    )
    task1.in_stream.buffer_size = DAQ_BUFFER
    task1.in_stream.read_all_available = False  # 只读固定点数，防溢出

    # 配置 9239
    task2.ai_channels.add_ai_voltage_chan(
        physical_channel=CH_9239,
        min_val=RANGE_9239[0],
        max_val=RANGE_9239[1]
    )
    task2.timing.cfg_samp_clk_timing(
        rate=SAMPLE_RATE,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=DAQ_BUFFER
    )
    task2.in_stream.buffer_size = DAQ_BUFFER
    task2.in_stream.read_all_available = False

    # 启动任务
    task1.start()
    task2.start()
    print("采集已启动，按下 Ctrl+C 停止并保存数据")

    while True:
        # 固定点数读取
        d1 = np.array(task1.read(number_of_samples_per_channel=READ_SAMPLES))
        d2 = np.array(task2.read(number_of_samples_per_channel=READ_SAMPLES))

        # 生成本段时间轴
        t_chunk = np.linspace(
            t_now,
            t_now + READ_SAMPLES / SAMPLE_RATE,
            READ_SAMPLES,
            endpoint=False
        )
        t_now += READ_SAMPLES / SAMPLE_RATE

        # ========== 1. 存入【全量数据】(用于最终保存CSV) ==========
        full_t = np.concatenate([full_t, t_chunk])
        full_9234 = np.hstack([full_9234, d1])
        full_9239 = np.hstack([full_9239, d2])

        # ========== 2. 存入【视图数据】(用于实时绘图，限制长度) ==========
        t_buf = np.concatenate([t_buf, t_chunk])
        data_9234_view = np.hstack([data_9234_view, d1])
        data_9239_view = np.hstack([data_9239_view, d2])

        # 截断视图数据，只保留最新画面区间
        if len(t_buf) > VIEW_POINTS:
            t_buf = t_buf[-VIEW_POINTS:]
            data_9234_view = data_9234_view[:, -VIEW_POINTS:]
            data_9239_view = data_9239_view[:, -VIEW_POINTS:]

        # 降频刷新绘图
        plot_cnt += 1
        if plot_cnt >= PLOT_INTERVAL:
            plot_cnt = 0
            for i in range(4):
                lines_9234[i].set_data(t_buf, data_9234_view[i])
                lines_9239[i].set_data(t_buf, data_9239_view[i])
            ax1.relim()
            ax1.autoscale_view()
            ax2.relim()
            ax2.autoscale_view()
            fig.canvas.draw()
            fig.canvas.flush_events()

        time.sleep(0.0005)

except KeyboardInterrupt:
    print("\n>>> 检测到 Ctrl+C，停止采集，开始保存数据...")
except Exception as e:
    print(f"\n采集异常: {e}")
finally:
    # 安全关闭DAQ任务
    if not task1.is_task_done():
        task1.stop()
    if not task2.is_task_done():
        task2.stop()
    task1.close()
    task2.close()

    plt.ioff()
    plt.show()

    # ===================== 保存全量数据到CSV =====================
    # 拼接数据表：时间 + 9234 4通道 + 9239 4通道
    save_data = np.column_stack([full_t, full_9234.T, full_9239.T])
    # 表头
    header_list = [
        "时间(s)",
        "9234_ai0(V)","9234_ai1(V)","9234_ai2(V)","9234_ai3(V)",
        "9239_ai0(V)","9239_ai1(V)","9239_ai2(V)","9239_ai3(V)"
    ]

    # 写入CSV
    np.savetxt(
        "daq_full_data.csv",
        save_data,
        delimiter=",",
        header=",".join(header_list),
        comments="",
        fmt="%.6f"
    )
    print(f">>> 数据保存完成，文件：daq_full_data.csv")
    print(f">>> 总采样点数：{len(full_t)}，总时长：{full_t[-1]:.2f} s")
    print("程序已退出")