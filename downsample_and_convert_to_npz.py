import os
import numpy as np
import pandas as pd

# 你的“之前保存的csv”根目录（按实际改）
# 假设结构类似：
# CSV_ROOT/
#   OK/*.csv
#   NG/*.csv
CSV_ROOT = r".\data\02-转换csv"

# 新的训练数据输出目录
OUT_ROOT = r".\data\04-train_data_npz"

TARGET_ROWS = 100000


def downsample_by_index(df: pd.DataFrame, target_rows: int = TARGET_ROWS) -> pd.DataFrame:
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


def process_one_csv(csv_path: str, label: int):
    # 读取CSV（你之前导出的列名通常是：time, ax, ay, az）
    df = pd.read_csv(csv_path)

    # 兼容列名大小写/空格
    cols = {c.strip().lower(): c for c in df.columns}
    required = ["time", "ax", "ay", "az"]
    if not all(k in cols for k in required):
        raise ValueError(f"CSV列名不符合要求，期望包含 {required}，实际={list(df.columns)}")

    df = df[[cols["time"], cols["ax"], cols["ay"], cols["az"]]].copy()
    df.columns = ["time", "ax", "ay", "az"]

    # 转数值并清理
    for c in ["time", "ax", "ay", "az"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["time", "ax", "ay", "az"]).reset_index(drop=True)

    # 下采样到2w
    df = downsample_by_index(df, TARGET_ROWS)

    t = df["time"].to_numpy(dtype=np.float32)
    X = df[["ax", "ay", "az"]].to_numpy(dtype=np.float32)
    y = np.int64(label)

    return t, X, y


def convert_split(subdir: str, label: int):
    in_dir = os.path.join(CSV_ROOT, subdir)
    out_dir = os.path.join(OUT_ROOT, subdir)
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isdir(in_dir):
        print(f"[WARN] 输入目录不存在：{in_dir}")
        return

    files = [f for f in os.listdir(in_dir) if f.lower().endswith(".csv")]
    print(f"[{subdir}] files={len(files)}  in={in_dir} -> out={out_dir}")

    for fn in files:
        src = os.path.join(in_dir, fn)
        base = os.path.splitext(fn)[0]
        dst = os.path.join(out_dir, base + ".npz")
        try:
            t, X, y = process_one_csv(src, label=label)
            # 保存为npz（训练读取很快）
            np.savez_compressed(dst, t=t, X=X, y=y)
            print(f"  OK {fn} -> {os.path.basename(dst)} | X={X.shape}, t={t.shape}, y={int(y)}")
        except Exception as e:
            print(f"  FAIL {fn}: {e}")


def main():
    # 你也可以反过来定义：OK=0, NG=1，只要训练时一致即可
    convert_split("OK", label=1)
    convert_split("NG", label=0)
    print("完成")


if __name__ == "__main__":
    main()