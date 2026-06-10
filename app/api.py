import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from app.inference_service import InferenceService
from app.plc_client import PlcClient
from app.runtime_config import load_runtime_config
from app.service import DetectionService


class DetectRequest(BaseModel):
    command: str = "START_DETECT"
    excel_path: Optional[str] = None


runtime_config = load_runtime_config()
inference_service = InferenceService(runtime_config.model_path)
plc_client = PlcClient(
    mode=runtime_config.plc_mode,
    host=runtime_config.plc_host,
    port=runtime_config.plc_port,
    timeout_sec=runtime_config.plc_timeout_sec,
    read_response=runtime_config.plc_read_response,
)
detection_service = DetectionService(
    inference_service=inference_service,
    plc_client=plc_client,
    default_excel_path=runtime_config.excel_path,
)

app = FastAPI(title="Yanpu Detection Service", version="0.1.0")


@app.get("/health")
def health():
    return {
        "ok": True,
        "model_path": str(runtime_config.model_path),
        "plc_mode": runtime_config.plc_mode,
    }


@app.post("/detect")
def detect(payload: DetectRequest):
    excel_path = Path(payload.excel_path) if payload.excel_path else runtime_config.excel_path
    try:
        return detection_service.run_detection(command=payload.command, excel_path=excel_path)
    except Exception:
        logging.exception("Unexpected error in /detect")
        return {
            "ok": False,
            "error_code": "INTERNAL_ERROR",
            "message": "Unexpected server error",
        }
