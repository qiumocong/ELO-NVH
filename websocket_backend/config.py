import os
import torch

SAVE_DIR = "./logs"
os.makedirs(SAVE_DIR, exist_ok=True)

# ---------- PLC ----------
PLC_IP = "192.168.3.124"
PLC_PORT = 1025

# 公共寄存器
PLC_MODE_REG = "R10"           # 1自动, 2人工
PLC_PRODUCT_REG = "R11"        # 规格名（10个字）

# ---------- 心跳 ----------
HEARTBEAT_REG = "R999"        # 心跳寄存器（公共）
HEARTBEAT_INTERVAL = 1.0      # 心跳间隔（秒）

# 工位配置
STATIONS = {
    "left": {
        "barcode_start": "R100",
        "barcode_len": 40,
        "plc_cmd_reg": "R140",        # PLC写入命令，PC读取
        "pc_status_reg": "R150",      # PC写入状态，PLC读取
        "plc_data_reg": "R160",       # PLC写入其他数据
        "pc_result_reg": "R151",      # PC写入结果，PLC读取
        "pc_result_ready": "R152",    # PC结果就绪标志
        "manual_result_reg": "R141",  # PLC写入人工判定，PC读取
        "reset_reg": "R30.1",         # 重置信号寄存器 (bit)
        "accel_channels": "cDAQ1Mod1/ai0:2",
        "voltage_channel": "cDAQ1Mod3/ai0",
        "current_channel": "cDAQ1Mod3/ai2",
        "input_indices": [0, 1, 2],
    },
    "right": {
        "barcode_start": "R200",
        "barcode_len": 40,
        "plc_cmd_reg": "R240",
        "pc_status_reg": "R250",
        "plc_data_reg": "R260",
        "pc_result_reg": "R251",
        "pc_result_ready": "R252",
        "manual_result_reg": "R241",
        "reset_reg": "R30.2",         # 重置信号寄存器 (bit)
        "accel_channels": "cDAQ1Mod2/ai0:2",
        "voltage_channel": "cDAQ1Mod3/ai1",
        "current_channel": "cDAQ1Mod3/ai3",
        "input_indices": [0, 1, 2],
    }
}

# PLC命令定义 (PLC写入, PC读取)
PLC_CMD_IDLE = 0
PLC_CMD_READY = 100
PLC_CMD_START = 200
PLC_CMD_FIRST_END = 300
PLC_CMD_SECOND_START = 400
PLC_CMD_STOP = 900

# PC状态定义 (PC写入, PLC读取)
PC_STATUS_IDLE = 0
PC_STATUS_READY = 100
PC_STATUS_COLLECTING = 200
PC_STATUS_PROCESSING = 300
PC_STATUS_COMPLETE = 900
PC_STATUS_ERROR = 999

MODEL_IN_CH = len(STATIONS["left"]["input_indices"])
MODEL_NUM_CLASSES = 2

# ---------- NI 采集 ----------
SAMPLE_RATE = 4800
CHUNK_SAMPLES = 1000
MAX_COLLECT_TIME = 60.0
RANGE_9234 = (-50.0, 50.0)
SENSITIVITY = 100
SENSOR_OUTPUT_MAX = 10.0
VOLTAGE_SENSOR_MAX = 36.0
CURRENT_SENSOR_MAX = 30.0

# ---------- 模型 ----------
MODEL_DIR = os.path.join(SAVE_DIR, "models")
os.makedirs(MODEL_DIR, exist_ok=True)
DEFAULT_MODEL_PATH = os.path.join(MODEL_DIR, "default.pth")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ---------- 数据保存 ----------
DATA_SAVE_DIR = os.path.join(SAVE_DIR, "saved_data")
OK_DIRNAME = "OK"
NG_DIRNAME = "NG"
os.makedirs(DATA_SAVE_DIR, exist_ok=True)

# ---------- 训练参数 ----------
TRAIN_CONFIG = {
    "batch_size": 8,
    "epochs": 20,
    "lr": 1e-3,
    "weight_decay": 1e-4,
    "test_size": 0.15,
    "val_size": 0.15,
    "seed": 42,
    "num_workers": 4,
    "pin_memory": True,
    "max_len": None,
    "min_samples_per_spec": 5,
}