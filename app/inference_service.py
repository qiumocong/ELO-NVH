from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import torch

from config import CONFIG
from model import Accel1DCNN


class InferenceError(RuntimeError):
    pass


@dataclass
class InferenceOutput:
    result_label: str
    result_id: int
    confidence: float
    waveform: Dict[str, List[float]]
    rows: int


class InferenceService:
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.device = CONFIG["DEVICE"]
        self.model = self._load_model()

    def _load_model(self) -> Accel1DCNN:
        if not self.model_path.exists():
            raise InferenceError(f"Model file not found: {self.model_path}")

        model = Accel1DCNN(in_ch=CONFIG["CHANNELS"], num_classes=2).to(self.device)
        state = torch.load(str(self.model_path), map_location=self.device)
        model.load_state_dict(state)
        model.eval()
        return model

    def _read_excel(self, excel_path: Path) -> Tuple[pd.DataFrame, torch.Tensor]:
        if not excel_path.exists():
            raise InferenceError(f"Excel file not found: {excel_path}")

        try:
            if excel_path.suffix.lower() in {".xlsx", ".xls"}:
                df = pd.read_excel(excel_path, engine="openpyxl")
            else:
                df = pd.read_csv(excel_path)
        except Exception as exc:
            raise InferenceError(f"Failed to read data file: {exc}") from exc

        colmap = {c.strip().lower(): c for c in df.columns}
        required = ["ax", "ay", "az"]
        if not all(k in colmap for k in required):
            raise InferenceError(f"Expected columns {required}, got: {list(df.columns)}")

        out_df = pd.DataFrame()
        if "time" in colmap:
            out_df["time"] = pd.to_numeric(df[colmap["time"]], errors="coerce")
        else:
            out_df["time"] = list(range(len(df)))

        for axis in required:
            out_df[axis] = pd.to_numeric(df[colmap[axis]], errors="coerce")

        out_df = out_df.dropna(subset=["time", "ax", "ay", "az"]).reset_index(drop=True)
        if out_df.empty:
            raise InferenceError("No valid rows after numeric cleaning")

        features = torch.tensor(out_df[["ax", "ay", "az"]].values, dtype=torch.float32)
        input_tensor = features.permute(1, 0).unsqueeze(0).to(self.device)
        return out_df, input_tensor

    def predict(self, excel_path: Path) -> InferenceOutput:
        out_df, input_tensor = self._read_excel(excel_path)
        with torch.no_grad():
            logits = self.model(input_tensor)
            probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            pred = int(probs.argmax())

        label = "OK" if pred == 0 else "NG"
        waveform = {
            "time": out_df["time"].astype(float).tolist(),
            "ax": out_df["ax"].astype(float).tolist(),
            "ay": out_df["ay"].astype(float).tolist(),
            "az": out_df["az"].astype(float).tolist(),
        }
        return InferenceOutput(
            result_label=label,
            result_id=pred,
            confidence=float(probs[pred]),
            waveform=waveform,
            rows=len(out_df),
        )

