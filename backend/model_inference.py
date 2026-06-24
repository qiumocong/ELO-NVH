import torch
import numpy as np
from model import Accel1DCNN   # 假设 model.py 已存在

def load_model(model_path, in_ch, num_classes, device):
    model = Accel1DCNN(in_ch=in_ch, num_classes=num_classes).to(device)
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()
    return model

def preprocess_data(data_8ch, input_indices):
    """从 8 通道数据中提取指定通道，并转换为 [1, channels, seq_len] 张量"""
    selected = data_8ch[input_indices, :]   # [ch, seq]
    tensor = torch.tensor(selected, dtype=torch.float32).unsqueeze(0)  # [1, ch, seq]
    return tensor

def predict(model, data_tensor, device):
    with torch.no_grad():
        logits = model(data_tensor.to(device))
        pred = torch.argmax(logits, dim=1).item()
    return pred