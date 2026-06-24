import os
import torch

# ---------- 路径 ----------
SAVE_DIR = "./logs"
os.makedirs(SAVE_DIR, exist_ok=True)

# ---------- PLC ----------
PLC_IP = "192.168.3.124"
PLC_PORT = 1025

PLC_MODE_REG = "R10"           # 1自动, 2人工
PLC_PRODUCT_REG = "R11"        # 规格名（10个字）

# 工位配置（包含NI通道和模型输入索引）
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
        # 模型输入使用哪些通道（从采集数据中选取，索引对应合并后的顺序：加速度在前，电压在后）
        # 这里只取x,z加速度，即索引0,1
        "input_indices": [0, 1],
    },
    "right": {
        "barcode_start": "R200",
        "barcode_len": 40,
        "plc_step_reg": "R240",
        "manual_result_reg": "R241",
        "pc_step_reg": "R250",
        "auto_result_reg": "R251",
        "accel_channels": "cDAQ1Mod1/ai2:3",   # 9234 通道2,3
        "voltage_channels": "cDAQ1Mod2/ai2:3", # 9239 通道2,3
        "input_indices": [0, 1],
    }
}

# 模型输入通道数（左右必须一致，此处为2）
MODEL_IN_CH = len(STATIONS["left"]["input_indices"])

# 步骤定义（与PLC协定）
STEP_READY = 100
STEP_TEST_START = 200
STEP_TEST_FIRST_END = 300
STEP_TEST_SECOND_START = 400
STEP_TEST_END = 900

# ---------- NI 采集公共参数 ----------
SAMPLE_RATE = 4800
CHUNK_SAMPLES = 1000
MAX_COLLECT_TIME = 60.0

# 9234 加速度计参数
RANGE_9234 = (-50.0, 50.0)
SENSITIVITY = 100                # mV/g
# 9239 电压参数
RANGE_9239 = (-10.0, 10.0)

# ---------- 模型 ----------
MODEL_PATH = os.path.join(SAVE_DIR, "best_model.pth")
MODEL_NUM_CLASSES = 2
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ---------- 数据保存 ----------
DATA_SAVE_DIR = os.path.join(SAVE_DIR, "saved_data")
OK_DIRNAME = "OK"
NG_DIRNAME = "NG"
# 注意：新的保存逻辑会在内部创建子目录，此处只确保根目录存在
os.makedirs(DATA_SAVE_DIR, exist_ok=True)