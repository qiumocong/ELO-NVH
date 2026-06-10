from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
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

    @staticmethod
    def _normalize_col_name(col) -> str:
        return str(col).strip().lower().replace("\u00a0", " ")

    @staticmethod
    def _downsample_by_index(df: pd.DataFrame, target_rows: int = 100000) -> pd.DataFrame:
        n = len(df)
        if n <= target_rows:
            return df.reset_index(drop=True)

        idx = np.linspace(0, n - 1, target_rows).round().astype(int)
        idx = np.unique(idx)

        if len(idx) < target_rows:
            missing = target_rows - len(idx)
            extra = np.setdiff1d(np.arange(n), idx)
            extra_pick = np.linspace(0, len(extra) - 1, missing).round().astype(int)
            idx = np.sort(np.concatenate([idx, extra[extra_pick]]))

        return df.iloc[idx].reset_index(drop=True)

    def _extract_from_standard_table(self, df: pd.DataFrame) -> pd.DataFrame:
        colmap = {self._normalize_col_name(c): c for c in df.columns}
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
        return out_df

    def _extract_from_raw_excel(self, raw: pd.DataFrame) -> pd.DataFrame:
        def norm(v) -> str:
            return self._normalize_col_name(v)

        def to_int(v):
            if v is None:
                return None
            try:
                return int(float(str(v).strip()))
            except Exception:
                return None

        max_r = min(200, len(raw))
        max_c = min(30, raw.shape[1])
        meta = {"first_row": None, "data_rows": None, "data_cols": None}
        meta_alias = {
            "first row:": "first_row",
            "data rows:": "data_rows",
            "data cols:": "data_cols",
        }

        for r in range(max_r):
            for c in range(max_c):
                text = norm(raw.iat[r, c])
                if text in meta_alias:
                    key = meta_alias[text]
                    val = None
                    for cc in range(c + 1, min(c + 6, max_c)):
                        val = to_int(raw.iat[r, cc])
                        if val is not None:
                            break
                    meta[key] = val

        if any(meta[k] is None for k in ("first_row", "data_rows", "data_cols")):
            raise InferenceError("Excel metadata is incomplete (First row/Data rows/Data cols)")

        max_scan_rows = min(200, len(raw))
        max_scan_cols = min(50, raw.shape[1])
        xyz_cols = None
        xyz_row = None
        for r in range(max_scan_rows):
            found = {}
            for c in range(max_scan_cols):
                cell = norm(raw.iat[r, c])
                if cell.endswith(" x"):
                    found.setdefault("x", c)
                elif cell.endswith(" y"):
                    found.setdefault("y", c)
                elif cell.endswith(" z"):
                    found.setdefault("z", c)
            if all(k in found for k in ("x", "y", "z")):
                xyz_row = r
                xyz_cols = found
                break
        if xyz_cols is None or xyz_row is None:
            raise InferenceError("Failed to locate xyz header row in Excel")

        t_col = None
        for r in range(xyz_row, max(-1, xyz_row - 30), -1):
            for c in range(max_scan_cols):
                if norm(raw.iat[r, c]) == "t":
                    t_col = c
                    break
            if t_col is not None:
                break
        if t_col is None:
            raise InferenceError("Failed to locate time column marker 't' in Excel")

        data_start = int(meta["first_row"]) - 1
        if data_start < 0 or data_start >= len(raw):
            raise InferenceError(f"Invalid first_row in Excel metadata: {meta['first_row']}")
        data_end = min(len(raw), data_start + int(meta["data_rows"]))

        out_df = raw.iloc[data_start:data_end, [t_col, xyz_cols["x"], xyz_cols["y"], xyz_cols["z"]]].copy()
        out_df.columns = ["time", "ax", "ay", "az"]
        for col in ["time", "ax", "ay", "az"]:
            out_df[col] = pd.to_numeric(out_df[col], errors="coerce")
        out_df = out_df.dropna(subset=["time", "ax", "ay", "az"]).reset_index(drop=True)

        if int(meta["data_cols"]) != 3:
            raise InferenceError(f"Expected Data cols=3 in Excel metadata, got {meta['data_cols']}")
        if len(out_df) < int(0.95 * int(meta["data_rows"])):
            raise InferenceError(
                f"Too few valid rows after Excel cleaning: expected≈{meta['data_rows']}, got={len(out_df)}"
            )
        return out_df

    def _read_excel(self, excel_path: Path) -> Tuple[pd.DataFrame, torch.Tensor]:
        if not excel_path.exists():
            raise InferenceError(f"Excel file not found: {excel_path}")

        try:
            if excel_path.suffix.lower() in {".xlsx", ".xls"}:
                raw = pd.read_excel(excel_path, header=None, engine="openpyxl")
                try:
                    out_df = self._extract_from_raw_excel(raw)
                except InferenceError:
                    df = pd.read_excel(excel_path, engine="openpyxl")
                    out_df = self._extract_from_standard_table(df)
            else:
                df = pd.read_csv(excel_path)
                out_df = self._extract_from_standard_table(df)
        except Exception as exc:
            raise InferenceError(f"Failed to read data file: {exc}") from exc

        out_df = self._downsample_by_index(out_df)

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
