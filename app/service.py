from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.inference_service import InferenceError, InferenceService
from app.plc_client import PlcClient, PlcError


class DetectionService:
    def __init__(self, inference_service: InferenceService, plc_client: PlcClient, default_excel_path: Path):
        self.inference_service = inference_service
        self.plc_client = plc_client
        self.default_excel_path = default_excel_path

    def run_detection(self, command: str, excel_path: Optional[Path] = None) -> Dict:
        now = datetime.now(timezone.utc).isoformat()

        try:
            plc_result = self.plc_client.send_command(command)
        except PlcError as exc:
            return {
                "ok": False,
                "error_code": "PLC_ERROR",
                "message": str(exc),
                "timestamp": now,
            }

        try:
            result = self.inference_service.predict(excel_path or self.default_excel_path)
        except InferenceError as exc:
            return {
                "ok": False,
                "error_code": "INFERENCE_ERROR",
                "message": str(exc),
                "timestamp": now,
                "plc": plc_result.__dict__,
            }

        return {
            "ok": True,
            "timestamp": now,
            "plc": plc_result.__dict__,
            "result": {
                "label": result.result_label,
                "label_id": result.result_id,
                "confidence": result.confidence,
                "rows": result.rows,
            },
            "waveform": result.waveform,
        }
