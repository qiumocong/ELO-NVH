import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class RuntimeConfig:
    model_path: Path
    excel_path: Path
    backend_host: str
    backend_port: int
    plc_mode: str
    plc_host: str
    plc_port: int
    plc_timeout_sec: float
    plc_read_response: bool


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        model_path=Path(os.getenv("YANPU_MODEL_PATH", str(PROJECT_ROOT / "logs" / "best_model.pth"))),
        excel_path=Path(os.getenv("YANPU_EXCEL_PATH", str(PROJECT_ROOT / "data" / "latest.xlsx"))),
        backend_host=os.getenv("YANPU_BACKEND_HOST", "127.0.0.1"),
        backend_port=int(os.getenv("YANPU_BACKEND_PORT", "8000")),
        plc_mode=os.getenv("YANPU_PLC_MODE", "mock").lower(),
        plc_host=os.getenv("YANPU_PLC_HOST", "127.0.0.1"),
        plc_port=int(os.getenv("YANPU_PLC_PORT", "5020")),
        plc_timeout_sec=float(os.getenv("YANPU_PLC_TIMEOUT_SEC", "2.0")),
        plc_read_response=os.getenv("YANPU_PLC_READ_RESPONSE", "1") == "1",
    )

