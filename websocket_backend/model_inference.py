import torch
import os
from model import Accel1DCNN
from config import DEVICE, MODEL_IN_CH, MODEL_NUM_CLASSES, MODEL_DIR, DEFAULT_MODEL_PATH, STATIONS

_model_cache = {}

def get_model_for_spec(spec_name):
    if spec_name in _model_cache:
        return _model_cache[spec_name]
    model_path = os.path.join(MODEL_DIR, f"{spec_name}.pth")
    if not os.path.exists(model_path):
        if os.path.exists(DEFAULT_MODEL_PATH):
            model_path = DEFAULT_MODEL_PATH
        else:
            print(f"警告: 规格 {spec_name} 的模型不存在，且无默认模型，将使用新初始化的模型")
            model = Accel1DCNN(MODEL_IN_CH, MODEL_NUM_CLASSES).to(DEVICE)
            model.eval()
            _model_cache[spec_name] = model
            return model
    model = Accel1DCNN(MODEL_IN_CH, MODEL_NUM_CLASSES).to(DEVICE)
    model.load_state_dict(torch.load(model_path, map_location=DEVICE))
    model.eval()
    _model_cache[spec_name] = model
    return model

def preprocess(data, station_name):
    indices = STATIONS[station_name]["input_indices"]  # [0, 1, 2]
    selected = data[indices, :]  # 取 [x, y, z]
    return torch.tensor(selected, dtype=torch.float32).unsqueeze(0)

def predict(model, tensor):
    with torch.no_grad():
        logits = model(tensor.to(DEVICE))
        probs = torch.softmax(logits, dim=1)
        pred = torch.argmax(logits, dim=1).item()
        score = probs[0, pred].item()
        return pred, score