import os
import glob
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from sklearn.model_selection import train_test_split

from config import CONFIG


def _list_csv_files(csv_root: str):
    ok_dir = os.path.join(csv_root, CONFIG["OK_DIRNAME"])
    ng_dir = os.path.join(csv_root, CONFIG["NG_DIRNAME"])

    ok_files = sorted(glob.glob(os.path.join(ok_dir, "*.csv")))
    ng_files = sorted(glob.glob(os.path.join(ng_dir, "*.csv")))

    samples = [(p, CONFIG["LABEL_OK"]) for p in ok_files] + [(p, CONFIG["LABEL_NG"]) for p in ng_files]
    if not samples:
        raise RuntimeError(f"未找到CSV数据，请检查 CSV_ROOT={csv_root} 及 OK/NG 子目录。")
    return samples


def _per_channel_standardize(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """
    x: (C, T)
    每个样本、每个通道做 z-score。
    """
    mean = x.mean(axis=1, keepdims=True)
    std = x.std(axis=1, keepdims=True)
    return (x - mean) / (std + eps)


class AccelCSVDataset(Dataset):
    """
    直接读取 csv -> (C,T) float32
    """
    def __init__(self, samples):
        self.samples = samples

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        df = pd.read_csv(path)

        # 兼容列名大小写/空格
        colmap = {c.strip().lower(): c for c in df.columns}
        required = [c.lower() for c in CONFIG["CSV_COLUMNS"]]
        for c in required:
            if c not in colmap:
                raise ValueError(f"{os.path.basename(path)} 缺少列 {c}，实际列={list(df.columns)}")

        # 取数值并清洗
        time = pd.to_numeric(df[colmap["time"]], errors="coerce").to_numpy()
        ax = pd.to_numeric(df[colmap["ax"]], errors="coerce").to_numpy()
        ay = pd.to_numeric(df[colmap["ay"]], errors="coerce").to_numpy()
        az = pd.to_numeric(df[colmap["az"]], errors="coerce").to_numpy()

        mask = np.isfinite(time) & np.isfinite(ax) & np.isfinite(ay) & np.isfinite(az)
        ax, ay, az = ax[mask], ay[mask], az[mask]
        if ax.size == 0:
            raise ValueError(f"{os.path.basename(path)} 清洗后无有效数据")

        X = np.stack([ax, ay, az], axis=0)  # (3,T)

        if CONFIG.get("USE_TIME"):
            t = time[mask]
            # 可选：把time做归一化后当第4通道
            t = (t - t.min()) / (t.max() - t.min() + 1e-9)
            X = np.concatenate([X, t[None, :]], axis=0)  # (4,T)

        # 可选：截断超长
        max_len = CONFIG.get("MAX_LEN")
        if max_len is not None and X.shape[1] > max_len:
            X = X[:, :max_len]

        # 标准化（非常建议）
        X = _per_channel_standardize(X).astype(np.float32)

        return torch.from_numpy(X), torch.tensor(label, dtype=torch.long), X.shape[1]


def collate_pad(batch):
    """
    batch: list of (X(C,T_i), y, len)
    -> X_pad: (B,C,T_max), y: (B,), lengths:(B,)
    """
    xs, ys, lens = zip(*batch)
    C = xs[0].shape[0]
    T_max = max(lens)

    x_pad = torch.zeros(len(xs), C, T_max, dtype=torch.float32)
    for i, x in enumerate(xs):
        t = x.shape[1]
        x_pad[i, :, :t] = x

    y = torch.stack(list(ys))
    lengths = torch.tensor(lens, dtype=torch.long)
    return x_pad, y, lengths


def _make_weighted_sampler(labels: np.ndarray):
    """
    仍保留此函数（如果你以后取消固定20/20，仍可以用加权采样）。
    """
    labels = np.asarray(labels)
    ok = np.sum(labels == CONFIG["LABEL_OK"])
    ng = np.sum(labels == CONFIG["LABEL_NG"])
    ok = max(int(ok), 1)
    ng = max(int(ng), 1)
    w_ok = 1.0 / ok
    w_ng = 1.0 / ng
    weights = np.array([w_ng if y == CONFIG["LABEL_NG"] else w_ok for y in labels], dtype=np.float64)
    return WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)


def _subsample_train_fixed(train_samples, ok_n: int, ng_n: int, seed: int):
    """
    只对训练集做固定抽样：OK=ok_n，NG=ng_n；验证/测试不动。
    """
    rng = np.random.default_rng(seed)
    ok = [(p, y) for (p, y) in train_samples if y == CONFIG["LABEL_OK"]]
    ng = [(p, y) for (p, y) in train_samples if y == CONFIG["LABEL_NG"]]

    if len(ok) < ok_n or len(ng) < ng_n:
        raise ValueError(f"训练集样本不足以固定抽样：OK需要{ok_n}但只有{len(ok)}；NG需要{ng_n}但只有{len(ng)}")

    ok_idx = rng.choice(len(ok), size=ok_n, replace=False)
    ng_idx = rng.choice(len(ng), size=ng_n, replace=False)

    fixed = [ok[i] for i in ok_idx] + [ng[i] for i in ng_idx]
    rng.shuffle(fixed)
    return fixed


def get_dataloaders():
    samples = _list_csv_files(CONFIG["CSV_ROOT"])

    if CONFIG.get("MAX_SAMPLES") is not None:
        samples = samples[: CONFIG["MAX_SAMPLES"]]

    paths = [p for p, _ in samples]
    labels = np.array([y for _, y in samples], dtype=np.int64)

    strat = labels if CONFIG["STRATIFY"] else None
    trainval_paths, test_paths, trainval_labels, test_labels = train_test_split(
        paths, labels, test_size=CONFIG["TEST_SIZE"], random_state=CONFIG["SEED"], stratify=strat
    )

    val_ratio_in_trainval = CONFIG["VAL_SIZE"] / (1.0 - CONFIG["TEST_SIZE"])
    strat2 = trainval_labels if CONFIG["STRATIFY"] else None
    train_paths, val_paths, train_labels, val_labels = train_test_split(
        trainval_paths, trainval_labels, test_size=val_ratio_in_trainval,
        random_state=CONFIG["SEED"], stratify=strat2
    )

    train_samples = list(zip(train_paths, train_labels.tolist()))
    val_samples = list(zip(val_paths, val_labels.tolist()))
    test_samples = list(zip(test_paths, test_labels.tolist()))

    # ===== 新增：训练集固定为 20OK + 20NG（验证/测试不变）=====
    # ok_n = int(CONFIG.get("TRAIN_OK_N", 20))
    # ng_n = int(CONFIG.get("TRAIN_NG_N", 20))
    # train_samples = _subsample_train_fixed(train_samples, ok_n=ok_n, ng_n=ng_n, seed=CONFIG["SEED"])

    # 打印统计
    train_y = np.array([y for _, y in train_samples], dtype=np.int64)
    val_y = np.array([y for _, y in val_samples], dtype=np.int64)
    test_y = np.array([y for _, y in test_samples], dtype=np.int64)

    print(f"样本数: train={len(train_samples)} val={len(val_samples)} test={len(test_samples)}")
    print(f"训练集类别统计(固定抽样后): OK={np.sum(train_y==0)} NG={np.sum(train_y==1)}")
    print(f"验证集类别统计: OK={np.sum(val_y==0)} NG={np.sum(val_y==1)}")
    print(f"测试集类别统计: OK={np.sum(test_y==0)} NG={np.sum(test_y==1)}")

    train_ds = AccelCSVDataset(train_samples)
    val_ds = AccelCSVDataset(val_samples)
    test_ds = AccelCSVDataset(test_samples)

    # 训练集已经平衡，不建议再用 WeightedRandomSampler
    train_loader = DataLoader(
        train_ds,
        batch_size=CONFIG["BATCH_SIZE"],
        shuffle=True,
        num_workers=CONFIG["NUM_WORKERS"],
        pin_memory=CONFIG["PIN_MEMORY"],
        collate_fn=collate_pad,
        drop_last=False,
    )

    val_loader = DataLoader(
        val_ds,
        batch_size=CONFIG["BATCH_SIZE"],
        shuffle=False,
        num_workers=CONFIG["NUM_WORKERS"],
        pin_memory=CONFIG["PIN_MEMORY"],
        collate_fn=collate_pad,
        drop_last=False,
    )

    test_loader = DataLoader(
        test_ds,
        batch_size=CONFIG["BATCH_SIZE"],
        shuffle=False,
        num_workers=CONFIG["NUM_WORKERS"],
        pin_memory=CONFIG["PIN_MEMORY"],
        collate_fn=collate_pad,
        drop_last=False,
    )

    return train_loader, val_loader, test_loader
