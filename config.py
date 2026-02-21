import torch
import os

# 创建保存目录
SAVE_DIR = "./logs"
os.makedirs(SAVE_DIR, exist_ok=True)

CONFIG = {
    # ================= 路径配置 =================
    "CSV_PATH": "./DATA_Processed_All/labels.csv", # 建议使用清洗后的 labels_cleaned.csv
    "SAVE_DIR": SAVE_DIR,
    "MODEL_SAVE_PATH": os.path.join(SAVE_DIR, "best_model.pth"),

    # === 新增调试参数 ===
    # 设置为 1000 表示只使用 1000 条数据进行快速训练测试
    # 设置为 None 表示使用全部数据
    "MAX_SAMPLES": 1000,
    
    # ================= 音频参数 =================
    "SAMPLE_RATE": 22050,
    # 设定长度 (请确保根据 clean_dataset.py 的结果进行了更新)
    "LEN_CW": 110000,   
    "LEN_CCW": 150000,  
    # 总输入长度 = CW + CCW
    "TOTAL_LEN": 260000, 
    
    # ================= 训练超参数 =================
    "BATCH_SIZE": 4,
    "EPOCHS": 30,
    "LR": 0.001,
    "NUM_WORKERS": 8,   # 根据CPU核心数调整
    "DEVICE": torch.device("cuda" if torch.cuda.is_available() else "cpu")
}