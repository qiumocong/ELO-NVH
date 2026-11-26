"""T2：独立保存缩放副本，不导入配置、PLC/NI、Qt 或推理模块。

调用者传入已经确定的安全规格/条码名，以及 STEP900 冻结的比例。
本模块不决定轮次、不生成条码、不保存原始文件，也不操作采集缓存。
metadata 可传入 original_dir、side、round_id 等 JSON 字段，保存在 source 中。
只有 metadata.json 中 status == 'saved' 且 completed == true 才是完整副本。
"""

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ScaledCopyResult:
    """failed 的 error 可直接用于调用方日志；directory 未确定时为 None。"""

    status: str  # saved / skipped / failed
    directory: Optional[Path] = None
    scale: Optional[float] = None
    error: Optional[str] = None


# 固定数量的进程内锁，避免长期采集时按条码无限积累锁对象。
# 路径大小写/符号链接先归一化；同一目录必定串行，不同目录可能共用一把锁。
# 不提供跨进程写入协调：一个副本根目录应由一个后端进程负责。
_TARGET_LOCKS = tuple(threading.Lock() for _ in range(64))


def _target_lock(directory):
    key = os.path.normcase(os.path.realpath(directory))
    return _TARGET_LOCKS[hash(key) % len(_TARGET_LOCKS)]


def _normalize_scale(scale):
    if isinstance(scale, (bool, np.bool_)):
        raise ValueError("scale 必须是 0.01～10 的有限数值，不能是布尔值")
    value = Decimal(str(scale))
    if not value.is_finite() or not Decimal("0.01") <= value <= Decimal("10"):
        raise ValueError("scale 必须是 0.01～10 的有限数值")
    # 与界面的整数百分比统一：乘数保留两位小数，计算/目录/元数据共用此值。
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(value), format(value.normalize(), "f")


def _validate_name(value, field):
    # 复用调用方的安全名称，禁止路径层级；不能再次清洗或另造空条码名称。
    if not isinstance(value, str) or not value or not all(
        c.isalnum() or c in ("_", "-") for c in value
    ):
        raise ValueError("{} 必须是已确定的非空安全名称（字母、数字、_、-）".format(field))
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update("COM{}".format(n) for n in range(1, 10))
    reserved.update("LPT{}".format(n) for n in range(1, 10))
    if value.upper() in reserved:
        raise ValueError("{} 不能使用 Windows 设备保留名".format(field))


def _snapshot_data(times, raw_data, scale):
    times_copy = np.array(times, copy=True)
    data_copy = np.array(raw_data, copy=True)
    if times_copy.ndim != 1 or data_copy.shape != (5, times_copy.size):
        raise ValueError("times 必须为 (N,)，raw_data 必须为 (5, N)，且长度相同")
    if times_copy.size == 0:
        raise ValueError("不能保存空数据")
    for name, values in (("times", times_copy), ("raw_data", data_copy)):
        if values.dtype.kind not in "iuf" or not np.isfinite(values).all():
            raise ValueError("{} 必须只包含有限实数".format(name))
    # 只把 XYZ 转为浮点副本；时间、电压和电流保留输入精度和原值。
    with np.errstate(over="raise", invalid="raise"):
        xyz = data_copy[:3].astype(np.result_type(data_copy.dtype, np.float64)) * scale
    if not np.isfinite(xyz).all():
        raise ValueError("XYZ 缩放后出现非有限值")
    return times_copy, data_copy, xyz


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _atomic_metadata(directory, record):
    """同目录临时写入后替换，避免 metadata.json 自身写到一半。"""
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory,
            prefix=".metadata-", suffix=".tmp", delete=False,
        ) as stream:
            pending = Path(stream.name)
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(pending, directory / "metadata.json")
    finally:
        if pending is not None and pending.exists():
            pending.unlink()


def write_scaled_copy(
    scaled_root, spec_name, label_name, barcode_name,
    times, raw_data, scale, metadata=None,
):
    """写入 <root>/<规格>/<比例>/<OK|NG>/<条码>/ch0.csv～ch4.csv。

    raw_data 顺序为 XYZ、电压、电流，形状 (5, N)，times 为 (N,)。
    比例按整数百分比规范化；为 1 时直接 skipped，不校验数据或创建目录。
    metadata 必须能序列化为严格 JSON；其副本写入 source，不能覆盖完成状态。
    返回 ScaledCopyResult，不把常规保存错误传播到 PLC 采集线程。

    五文件替换不是原子事务。覆盖前先撤销旧完成标记，失败保留 failed/未完成
    标记；断电也可能留下 incomplete。调用方/检查工具必须检查完成状态。
    若连未完成标记都写不进去，不替换任何通道，之前的完整副本保持原样。
    """
    directory = None
    normalized_scale = None
    try:
        normalized_scale, scale_name = _normalize_scale(scale)
        if normalized_scale == 1.0:
            return ScaledCopyResult("skipped", scale=normalized_scale)
        _validate_name(spec_name, "spec_name")
        _validate_name(barcode_name, "barcode_name")
        if label_name not in ("OK", "NG"):
            raise ValueError("label_name 必须为 OK 或 NG")
        if not os.fspath(scaled_root):
            raise ValueError("scaled_root 不能为空")
        # 先按规格归类，再集中存放该规格的各比例；已有旧层级文件不自动迁移。
        directory = Path(scaled_root) / spec_name / scale_name / label_name / barcode_name
        times_copy, data_copy, xyz = _snapshot_data(times, raw_data, normalized_scale)
        # JSON 往返同时校验可序列化性、复制嵌套字段；文件写入期间不再读原 metadata。
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata 必须为字典或 None")
        source = json.loads(json.dumps(metadata or {}, ensure_ascii=False, allow_nan=False))
        record = {
            "format_version": 1,
            "status": "incomplete",
            "completed": False,
            "scale": normalized_scale,
            "scale_directory": scale_name,
            "spec_name": spec_name,
            "label_name": label_name,
            "barcode_name": barcode_name,
            "sample_count": int(times_copy.size),
            "scaled_channels": [0, 1, 2],
            "started_at": _timestamp(),
            "source": source,
        }
        with _target_lock(directory):
            directory.mkdir(parents=True, exist_ok=True)
            # 先使旧完成标记失效；这一操作失败时，绝不开始覆盖通道文件。
            _atomic_metadata(directory, record)
            try:
                with tempfile.TemporaryDirectory(prefix=".scaled-write-", dir=directory) as staging:
                    staging = Path(staging)
                    for ch in range(5):
                        values = xyz[ch] if ch < 3 else data_copy[ch]
                        pd.DataFrame({"time": times_copy, "ch{}".format(ch): values}).to_csv(
                            staging / "ch{}.csv".format(ch), index=False,
                        )
                    # 全部准备成功后才替换；同盘 replace 对单个文件是原子操作。
                    for ch in range(5):
                        name = "ch{}.csv".format(ch)
                        os.replace(staging / name, directory / name)
                record.update(status="saved", completed=True, saved_at=_timestamp())
                _atomic_metadata(directory, record)
            except Exception as exc:
                record.update(status="failed", completed=False, error=str(exc))
                record.pop("saved_at", None)
                try:
                    _atomic_metadata(directory, record)
                except Exception as marker_error:
                    # 前面的 incomplete 已写好，即便失败说明也写不了，仍不会冒充成功。
                    raise OSError("{}；失败状态写入也失败：{}".format(exc, marker_error)) from exc
                raise
        return ScaledCopyResult("saved", directory, normalized_scale)
    except Exception as exc:
        return ScaledCopyResult("failed", directory, normalized_scale,
                                "{}: {}".format(type(exc).__name__, exc))
