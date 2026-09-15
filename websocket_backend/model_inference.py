import torch
import os
from model import Accel1DCNN
from config import DEVICE, MODEL_IN_CH, MODEL_NUM_CLASSES, MODEL_DIR, DEFAULT_MODEL_PATH, STATIONS

DEFAULT_THRESHOLD = 0.5

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
            model.threshold = DEFAULT_THRESHOLD
            _model_cache[spec_name] = model
            return model
    checkpoint = torch.load(model_path, map_location=DEVICE, weights_only=False)
    if isinstance(checkpoint, dict) and "model_state" in checkpoint:
        # train_from_saved_new.py 保存的格式：带阈值等元数据的完整 checkpoint
        state_dict = checkpoint["model_state"]
        threshold = float(checkpoint.get("threshold", DEFAULT_THRESHOLD))
    else:
        # train_from_saved.py 保存的旧格式：纯 state_dict
        state_dict = checkpoint
        threshold = DEFAULT_THRESHOLD
    model = Accel1DCNN(MODEL_IN_CH, MODEL_NUM_CLASSES).to(DEVICE)
    model.load_state_dict(state_dict)
    model.eval()
    model.threshold = threshold
    _model_cache[spec_name] = model
    return model

def preprocess(data, station_name):
    indices = STATIONS[station_name]["input_indices"]  # [0, 1, 2]
    selected = data[indices, :]  # 取 [x, y, z]
    return torch.tensor(selected, dtype=torch.float32).unsqueeze(0)

def predict(model, tensor):
    threshold = getattr(model, "threshold", DEFAULT_THRESHOLD)
    with torch.no_grad():
        logits = model(tensor.to(DEVICE))
        probs = torch.softmax(logits, dim=1)
        ng_prob = probs[0, 1].item()
        pred = 1 if ng_prob >= threshold else 0
        score = probs[0, pred].item()
        return pred, score