import os
import torch

# ---------- 通用路径 ----------
SAVE_DIR = "./logs"
os.makedirs(SAVE_DIR, exist_ok=True)

# ---------- 工作模式 ----------
MODE = "auto"           # "auto" : 自动检测推理 ; "manual" : 人工标注
PLOT_ENABLE = True      # 是否实时显示采集波形

# ---------- PLC 通信参数 ----------
PLC_IP = "192.168.1.100"
PLC_PORT = 5000

# PLC 寄存器地址（根据实际 PLC 程序修改）
PLC_STEP_REG = "D0"             # 存放 PLC 步骤值（只读）
PC_STEP_REG  = "D1"             # PC 写入的步骤值（用于握手）
PLC_BARCODE_REG = "D100"        # 条码字符串起始寄存器（占用多个字）
PLC_PRODUCT_REG = "D200"        # 产品规格数据（暂未使用）

# 结果输出寄存器（自动模式 PC 写入，手动模式 PLC 写入）
PLC_RESULT_REG = "D300"         # PC 写入判定结果（1=OK, 2=NG）
PLC_MANUAL_RESULT_REG = "D400"  # 人工判定结果（PLC 写入，PC 读取）

# 步骤值定义（与 PLC 协定）
STEP_READY = 100                # 双方就绪
STEP_TEST_START = 200           # 开始采集
STEP_TEST_FIRST_END = 300       # 第一段结束（仅握手）
STEP_TEST_SECOND_START = 400    # 第二段开始（仅握手）
STEP_TEST_END = 900             # 全部测试结束，PC 处理数据

# ---------- NI 采集参数 ----------
SAMPLE_RATE = 5000                      # 采样率 (Hz)
CHUNK_SAMPLES = 1000                    # 每帧读取点数
COLLECT_TIMEOUT = 60.0                  # 最大采集超时（秒），防止死等

# 物理通道（根据实际设备修改）
CH_9234 = "cDAQ1Mod1/ai0:3"             # 4 通道
CH_9239 = "cDAQ1Mod2/ai0:3"             # 4 通道
RANGE_9234 = (-5.0, 5.0)
RANGE_9239 = (-10.0, 10.0)

# 模型输入通道映射（从 8 个通道中选择 3 个作为 ax, ay, az）
# 索引：0-3 为 9234，4-7 为 9239
INPUT_CHANNEL_INDICES = [0, 1, 2]       # 使用 9234 的 ai0, ai1, ai2

# ---------- 模型参数 ----------
MODEL_PATH = os.path.join(SAVE_DIR, "best_model.pth")
MODEL_IN_CH = 3                         # 输入通道数（与 INPUT_CHANNEL_INDICES 长度一致）
MODEL_NUM_CLASSES = 2
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ---------- 数据保存 ----------
DATA_SAVE_DIR = os.path.join(SAVE_DIR, "saved_data")
os.makedirs(DATA_SAVE_DIR, exist_ok=True)
OK_DIRNAME = "OK"
NG_DIRNAME = "NG"
os.makedirs(os.path.join(DATA_SAVE_DIR, OK_DIRNAME), exist_ok=True)
os.makedirs(os.path.join(DATA_SAVE_DIR, NG_DIRNAME), exist_ok=True)

# ---------- 其他 ----------
SEED = 42