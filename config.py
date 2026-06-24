import os
import torch

SAVE_DIR = "./logs"
os.makedirs(SAVE_DIR, exist_ok=True)

CONFIG = {
    # CSV 数据根目录（按你的实际路径改）
    "CSV_ROOT": r"D:\CodeProject\PycharmProject\yanpu\data\02-转换csv",
    "OK_DIRNAME": "OK",
    "NG_DIRNAME": "NG",

    # 读取列名
    "CSV_COLUMNS": ["time", "ax", "ay", "az"],
    "USE_TIME": False,     # True 则输入通道=4，否则=3
    "CHANNELS": 3,         # USE_TIME=True 时请改成 4

    # 可变长度训练的控制：为避免超长序列OOM，可以设置最大长度截断
    # None = 不截断（可能很长，显存/内存压力大）
    "MAX_LEN": None,     # 建议先设一个上限；你也可改成 None

    # 标签
    "LABEL_OK": 0,
    "LABEL_NG": 1,

    "TRAIN_OK_N": 20,
    "TRAIN_NG_N": 20,

    # 切分
    "SEED": 42,
    "TEST_SIZE": 0.15,
    "VAL_SIZE": 0.15,
    "STRATIFY": True,
    "MAX_SAMPLES": None,   # debug用：只用前N个文件

    # 训练
    "BATCH_SIZE": 8,       # 可变长时一般batch要小
    "EPOCHS": 16,
    "LR": 1e-3,
    "WEIGHT_DECAY": 1e-4,
    "NUM_WORKERS": 4,
    "PIN_MEMORY": True,

    # 保存策略：按 NG recall 或 macro-F1
    "SAVE_METRIC": "macro_f1",  # "ng_recall" 或 "macro_f1"
    "MODEL_SAVE_PATH": os.path.join(SAVE_DIR, "best_model.pth"),
    "SAVE_DIR": SAVE_DIR,

    "DEVICE": torch.device("cuda" if torch.cuda.is_available() else "cpu"),
}

PLC_CONFIG = {
    ''
}