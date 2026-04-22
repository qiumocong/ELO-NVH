import io
import os
import numpy as np
import torch
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import CONFIG
from model import Accel1DCNN

app = FastAPI(title="加速度序列 OK/NG 检测系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

device = torch.device("cpu")
model = Accel1DCNN(in_ch=CONFIG["CHANNELS"], num_classes=2)
model_path = CONFIG["MODEL_SAVE_PATH"]

model_loaded = False
if os.path.exists(model_path):
    sd = torch.load(model_path, map_location=device)
    model.load_state_dict(sd)
    model_loaded = True
model.eval()


def _downsample_to_2w(X: np.ndarray, target_len: int = 20000) -> np.ndarray:
    # X: (T,3)
    T = X.shape[0]
    if T == target_len:
        return X
    if T > target_len:
        idx = np.linspace(0, T - 1, target_len).round().astype(np.int64)
        idx = np.unique(idx)
        if len(idx) < target_len:
            missing = target_len - len(idx)
            extra = np.setdiff1d(np.arange(T), idx)
            extra_pick = np.linspace(0, len(extra) - 1, missing).round().astype(np.int64)
            idx = np.sort(np.concatenate([idx, extra[extra_pick]]))
        return X[idx]
    pad = np.zeros((target_len - T, X.shape[1]), dtype=X.dtype)
    return np.concatenate([X, pad], axis=0)


@app.get("/api/status")
async def status():
    return JSONResponse({
        "model_loaded": model_loaded,
        "model_path": model_path,
        "channels": CONFIG["CHANNELS"],
        "target_len": CONFIG["TARGET_LEN"],
        "labels": {"OK": 0, "NG": 1},
    })


@app.post("/api/predict_npz")
async def predict_npz(file: UploadFile = File(..., description="上传单个样本 npz（包含 X: (T,3)）")):
    data = await file.read()
    buf = io.BytesIO(data)
    try:
        npz = np.load(buf, allow_pickle=False)
        if "X" not in npz:
            return JSONResponse({"error": "npz 中缺少 X"}, status_code=400)
        X = npz["X"]
        if X.ndim != 2 or X.shape[1] != CONFIG["CHANNELS"]:
            return JSONResponse({"error": f"X shape 不正确: {X.shape}"}, status_code=400)

        X = _downsample_to_2w(X.astype(np.float32), CONFIG["TARGET_LEN"])  # (20000,3)
        X_t = torch.from_numpy(X.T).unsqueeze(0)  # (1,3,20000)

        if not model_loaded:
            return JSONResponse({"error": "模型未加载，请先训练生成 best_model.pth"}, status_code=500)

        with torch.no_grad():
            logits = model(X_t.to(device))
            probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
            pred = int(np.argmax(probs))
            ok_p = float(probs[0])
            ng_p = float(probs[1])

        return JSONResponse({
            "result": "NG" if pred == 1 else "OK",
            "pred": pred,
            "probabilities": {"OK": ok_p, "NG": ng_p},
            "confidence": ng_p if pred == 1 else ok_p,
            "model_loaded": model_loaded
        })
    except Exception as e:
        return JSONResponse({"error": f"解析/预测失败: {e}"}, status_code=400)


# 静态前端
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")