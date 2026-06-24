import torch
import numpy as np
from model import Accel1DCNN
from config import DEVICE, MODEL_IN_CH, MODEL_NUM_CLASSES, MODEL_PATH, STATIONS

def load_model():
    model = Accel1DCNN(MODEL_IN_CH, MODEL_NUM_CLASSES).to(DEVICE)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
    model.eval()
    return model

def preprocess(data_8ch, station_name):
    """根据工位名称提取对应的输入通道（只含加速度x,z）"""
    indices = STATIONS[station_name]["input_indices"]
    selected = data_8ch[indices, :]          # [chan, seq_len]
    tensor = torch.tensor(selected, dtype=torch.float32).unsqueeze(0)  # [1, chan, seq]
    return tensor

def predict(model, tensor):
    with torch.no_grad():
        logits = model(tensor.to(DEVICE))
        # 简单返回argmax，置信度可通过softmax获得，此处暂未实现
        return torch.argmax(logits, dim=1).item()   # 0=OK, 1=NG