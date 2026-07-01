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
HEARTBEAT_INTERVAL = 3.0      # 心跳间隔（秒）

# 工位配置
STATIONS = {
    "left": {
        "barcode_start": "R100",
        "barcode_len": 40,
        "plc_cmd_reg": "R140",
        "pc_status_reg": "R150",
        "pc_result_reg": "R151",
        "pc_result_ready": "R152",
        "manual_result_reg": "R141",
        "reset_reg": "R30.1",
        "data_ready_reg": "R30.3",
        "accel_channels": "cDAQ1Mod1/ai0:2",
        # 左工位: 电压=AI2, 电流=AI3
        "voltage_channel": "cDAQ1Mod3/ai2",
        "current_channel": "cDAQ1Mod3/ai3",
        "input_indices": [0, 1, 2],
    },
    "right": {
        "barcode_start": "R200",
        "barcode_len": 40,
        "plc_cmd_reg": "R240",
        "pc_status_reg": "R250",
        "pc_result_reg": "R251",
        "pc_result_ready": "R252",
        "manual_result_reg": "R241",
        "reset_reg": "R30.2",
        "data_ready_reg": "R30.4",
        "accel_channels": "cDAQ1Mod2/ai0:2",
        # 右工位: 电压=AI0, 电流=AI1
        "voltage_channel": "cDAQ1Mod3/ai0",
        "current_channel": "cDAQ1Mod3/ai1",
        "input_indices": [0, 1, 2],
    }
}

# PLC命令定义
PLC_CMD_IDLE = 0
PLC_CMD_READY = 100
PLC_CMD_START = 200
PLC_CMD_FIRST_END = 300
PLC_CMD_SECOND_START = 400
PLC_CMD_STOP = 900

# PC状态定义
PC_STATUS_IDLE = 0
PC_STATUS_READY = 100
PC_STATUS_COLLECTING = 200
PC_STATUS_PROCESSING = 300
PC_STATUS_COMPLETE = 900
PC_STATUS_ERROR = 999

MODEL_IN_CH = len(STATIONS["left"]["input_indices"])
MODEL_NUM_CLASSES = 2

# ---------- NI 采集 ----------
SAMPLE_RATE = 2400
CHUNK_SAMPLES = 500
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
# DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DEVICE = torch.device("cpu")

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