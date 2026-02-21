import io
import logging
import os
import random

import torch
import torchaudio
from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from model import FusedMotorClassifier
from config import CONFIG

app = FastAPI(title="电机音频质量检测系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------- 模型加载 ---------------
device = torch.device("cpu")
model = FusedMotorClassifier()
model_loaded = False

model_path = CONFIG["MODEL_SAVE_PATH"]
if os.path.exists(model_path):
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model_loaded = True
    print(f"✅ 模型加载成功: {model_path}")
else:
    print(f"⚠️  未找到模型文件 ({model_path})，将使用演示模式")

model.eval()


# --------------- 辅助函数 ---------------

def _load_audio_from_bytes(data: bytes, target_len: int) -> torch.Tensor:
    """从字节流加载音频，转单声道，重采样，截断/补零到 target_len。"""
    try:
        buf = io.BytesIO(data)
        wf, sr = torchaudio.load(buf)
        # 多声道 → 单声道
        wf = torch.mean(wf, dim=0, keepdim=True)
        # 采样率不匹配时重采样
        if sr != CONFIG["SAMPLE_RATE"]:
            resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=CONFIG["SAMPLE_RATE"])
            wf = resampler(wf)
        # 截断或补零
        cur = wf.shape[1]
        if cur >= target_len:
            return wf[:, :target_len]
        return torch.nn.functional.pad(wf, (0, target_len - cur))
    except Exception as e:
        logger.warning("Failed to load audio: %s", e)
        return torch.zeros(1, target_len)


# --------------- API 路由 ---------------

@app.get("/api/status")
async def get_status():
    return JSONResponse({
        "model_loaded": model_loaded,
        "model_path": model_path,
        "sample_rate": CONFIG["SAMPLE_RATE"],
        "len_cw": CONFIG["LEN_CW"],
        "len_ccw": CONFIG["LEN_CCW"],
    })


@app.post("/api/predict")
async def predict(
    cw_x:  UploadFile = File(..., description="CW方向 X轴音频"),
    ccw_x: UploadFile = File(..., description="CCW方向 X轴音频"),
    cw_z:  UploadFile = File(..., description="CW方向 Z轴音频"),
    ccw_z: UploadFile = File(..., description="CCW方向 Z轴音频"),
):
    cw_x_bytes  = await cw_x.read()
    ccw_x_bytes = await ccw_x.read()
    cw_z_bytes  = await cw_z.read()
    ccw_z_bytes = await ccw_z.read()

    cw_x_t  = _load_audio_from_bytes(cw_x_bytes,  CONFIG["LEN_CW"])
    ccw_x_t = _load_audio_from_bytes(ccw_x_bytes, CONFIG["LEN_CCW"])
    cw_z_t  = _load_audio_from_bytes(cw_z_bytes,  CONFIG["LEN_CW"])
    ccw_z_t = _load_audio_from_bytes(ccw_z_bytes, CONFIG["LEN_CCW"])

    # (1, LEN_CW+LEN_CCW) × 2 → (1, 2, TOTAL_LEN)
    full_x = torch.cat([cw_x_t,  ccw_x_t], dim=1)
    full_z = torch.cat([cw_z_t,  ccw_z_t], dim=1)
    tensor  = torch.cat([full_x, full_z], dim=0).unsqueeze(0)  # (1,2,TOTAL_LEN)

    if model_loaded:
        with torch.no_grad():
            logits = model(tensor.to(device))
            probs  = torch.softmax(logits, dim=1).squeeze()
            pred   = int(torch.argmax(probs).item())
            ok_p   = float(probs[0])
            ng_p   = float(probs[1])
    else:
        # 演示模式：模拟随机结果
        pred = random.randint(0, 1)
        ok_p = round(random.uniform(0.6, 0.95), 4) if pred == 0 else round(random.uniform(0.05, 0.4), 4)
        ng_p = round(1.0 - ok_p, 4)

    result = "NG" if pred == 1 else "OK"

    return JSONResponse({
        "result": result,
        "confidence": ng_p if pred == 1 else ok_p,
        "probabilities": {"OK": ok_p, "NG": ng_p},
        "model_loaded": model_loaded,
    })


# --------------- 静态文件（前端） ---------------
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
