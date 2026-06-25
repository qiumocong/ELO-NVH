import os
import torch

SAVE_DIR = "./logs"
os.makedirs(SAVE_DIR, exist_ok=True)

# ---------- PLC ----------
PLC_IP = "192.168.3.124"
PLC_PORT = 1025
PLC_MODE_REG = "R10"
PLC_PRODUCT_REG = "R11"

# ---------- 心跳 ----------
HEARTBEAT_REG = "R999"        # 心跳寄存器（公共）
HEARTBEAT_INTERVAL = 1.0      # 心跳间隔（秒）

# 工位配置（增加NI通道和模型输入索引）
STATIONS = {
    "left": {
        "barcode_start": "R100",
        "barcode_len": 40,
        "plc_step_reg": "R140",
        "manual_result_reg": "R141",
        "pc_step_reg": "R150",
        "auto_result_reg": "R151",
        # 仅采集该工位使用的NI通道
        "accel_channels": "cDAQ1Mod1/ai0:1",   # 9234 通道0,1 (x,z)
        "voltage_channels": "cDAQ1Mod2/ai0:1", # 9239 通道0,1 (电流,电压)
        # 模型输入使用哪些通道（从上述采集的通道中选，索引对应采集到的数据顺序）
        # 采集数据顺序：[accel通道..., voltage通道...] -> 这里accel 2个 + voltage 2个 = 4个
        # 模型只取x,z加速度，即索引0,1
        "input_indices": [0, 1],
    },
    "right": {
        "barcode_start": "R200",
        "barcode_len": 40,
        "plc_step_reg": "R240",
        "manual_result_reg": "R241",
        "pc_step_reg": "R250",
        "auto_result_reg": "R251",
        "accel_channels": "cDAQ1Mod1/ai2:3",   # 9234 通道2,3 (x,z)
        "voltage_channels": "cDAQ1Mod2/ai2:3", # 9239 通道2,3 (电流,电压)
        "input_indices": [0, 1],               # 同样取加速度
    }
}

MODEL_IN_CH = len(STATIONS["left"]["input_indices"])
MODEL_NUM_CLASSES = 2

STEP_READY = 100
STEP_TEST_START = 200
STEP_TEST_FIRST_END = 300
STEP_TEST_SECOND_START = 400
STEP_TEST_END = 900

# ---------- NI 采集 ----------
SAMPLE_RATE = 4800
CHUNK_SAMPLES = 1000
MAX_COLLECT_TIME = 60.0
RANGE_9234 = (-50.0, 50.0)
SENSITIVITY = 100
RANGE_9239 = (-10.0, 10.0)

# ---------- 模型 ----------
MODEL_DIR = os.path.join(SAVE_DIR, "models")
os.makedirs(MODEL_DIR, exist_ok=True)
# 默认模型（当规格无专属模型时使用，可提前放置或留空）
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
    "min_samples_per_spec": 5,      # 少于该样本数则不训练
}