import os
import torch

SAVE_DIR = "./logs"
os.makedirs(SAVE_DIR, exist_ok=True)

# ---------- PLC ----------
PLC_IP = "192.168.3.124"
PLC_PORT = 1025

PLC_MODE_REG = "R10"           # 1自动, 2人工
PLC_PRODUCT_REG = "R11"        # 规格名（10个字）

# ---------- 心跳 ----------
HEARTBEAT_REG = "R999"
HEARTBEAT_INTERVAL = 1.0       # 秒

# ---------- PLC 操作参数 ----------
PLC_TIMEOUT = 3.0              # 单次操作超时（秒）
PLC_RETRIES = 3                # 操作失败重试次数
PLC_KEEPALIVE_INTERVAL = 2.0   # 后台保活探测间隔（秒）

# ---------- 工位配置（修正 9239 通道）----------
STATIONS = {
    "left": {
        "barcode_start": "R100",
        "barcode_len": 40,
        "plc_cmd_reg": "R140",
        "pc_status_reg": "R150",
        "plc_data_reg": "R160",
        "pc_result_reg": "R151",
        "pc_result_ready": "R152",
        "manual_result_reg": "R141",
        "reset_reg": "R30.1",
        # 修正：左电压 AI2，左电流 AI3
        "accel_channels": "cDAQ1Mod1/ai0:2",
        "voltage_channel": "cDAQ1Mod3/ai2",
        "current_channel": "cDAQ1Mod3/ai3",
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
        "reset_reg": "R30.2",
        # 修正：右电压 AI0，右电流 AI1
        "accel_channels": "cDAQ1Mod2/ai0:2",
        "voltage_channel": "cDAQ1Mod3/ai0",
        "current_channel": "cDAQ1Mod3/ai1",
        "input_indices": [0, 1, 2],
    }
}

# 通道添加顺序（必须与 _convert_data 中的索引匹配）
# 索引 0-2: 左加速度, 3-5: 右加速度, 6: 左电压, 7: 右电压, 8: 左电流, 9: 右电流
DAQ_ADD_ORDER = [
    "left_accel", "right_accel",
    "left_voltage", "right_voltage",
    "left_current", "right_current"
]

# PLC 命令定义
PLC_CMD_IDLE = 0
PLC_CMD_READY = 100
PLC_CMD_START = 200
PLC_CMD_FIRST_END = 300
PLC_CMD_SECOND_START = 400
PLC_CMD_STOP = 900

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
RANGE_9234 = (-50.0, 50.0)          # 加速度量程
SENSITIVITY = 100                    # mV/g
SENSOR_OUTPUT_MAX = 10.0             # 电压/电流传感器输出最大值（V）
VOLTAGE_SENSOR_MAX = 36.0            # 实际电压量程
CURRENT_SENSOR_MAX = 30.0            # 实际电流量程

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

# ---------- 工位运行参数 ----------
POLL_INTERVAL = 0.1                # 等待 PLC 命令时的轮询间隔（秒）
MANUAL_TIMEOUT = 30                # 人工判定超时（秒）

# ---------- WebSocket ----------
WS_PORT = 8081