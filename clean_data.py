import os
import re
import pandas as pd

OK_DIR = r"D:\qmc\PycharmProjects\yanpu\data\01-原始excel文件\OK"
NG_DIR = r"D:\qmc\PycharmProjects\yanpu\data\01-原始excel文件\NG"
OUT_ROOT = r"D:\qmc\PycharmProjects\yanpu\data\02-转换csv"

META_KEYS = {
    "first_row": re.compile(r"^\s*first\s*row\s*:\s*$", re.IGNORECASE),
    "data_rows": re.compile(r"^\s*data\s*rows\s*:\s*$", re.IGNORECASE),
    "data_cols": re.compile(r"^\s*data\s*cols\s*:\s*$", re.IGNORECASE),
}

T_CELL_PAT = re.compile(r"^\s*t\s*$", re.IGNORECASE)
XYZ_CELL_PAT = re.compile(r"^\s*\d*\s*([xyz])\s*$", re.IGNORECASE)


def norm(s) -> str:
    s = "" if s is None else str(s)
    return s.strip().lower().replace("\u00a0", " ")


def to_int(v):
    if v is None:
        return None
    try:
        # excel 里可能是 float
        return int(float(str(v).strip()))
    except Exception:
        return None


def is_number(x) -> bool:
    try:
        if x is None:
            return False
        float(x)
        return True
    except Exception:
        return False


def find_meta(raw: pd.DataFrame):
    """
    在前200行内找到 First row / Data rows / Data cols 对应的值。
    这些值通常在 key 单元格右侧紧邻的单元格中。
    """
    max_r = min(200, len(raw))
    max_c = min(30, raw.shape[1])

    meta = {"first_row": None, "data_rows": None, "data_cols": None}

    for r in range(max_r):
        for c in range(max_c):
            v = norm(raw.iat[r, c])
            if not v:
                continue

            for k, pat in META_KEYS.items():
                if pat.match(v):
                    # 值一般在右侧第1列（如果为空再往右找几格）
                    val = None
                    for cc in range(c + 1, min(c + 6, max_c)):
                        cand = raw.iat[r, cc]
                        val = to_int(cand)
                        if val is not None:
                            break
                    meta[k] = val

    if meta["first_row"] is None or meta["data_rows"] is None or meta["data_cols"] is None:
        raise ValueError(f"元信息未找全：{meta}（找不到 First row/Data rows/Data cols）")

    return meta


def find_xyz_header_row(raw: pd.DataFrame):
    """
    找到包含 x/y/z 的表头行（如：空, 244484 x, 244484 y, 244484 z）
    返回 (row_index, col_x, col_y, col_z)
    """
    max_scan_rows = min(200, len(raw))
    max_scan_cols = min(50, raw.shape[1])

    for r in range(max_scan_rows):
        row = [norm(raw.iat[r, c]) for c in range(max_scan_cols)]
        found = {}
        for c, v in enumerate(row):
            if not v:
                continue
            m = XYZ_CELL_PAT.match(v)
            if m:
                axis = m.group(1).lower()
                if axis not in found:
                    found[axis] = c
        if all(k in found for k in ("x", "y", "z")):
            return r, found["x"], found["y"], found["z"]

    raise ValueError("未找到 xyz 表头行（... x / ... y / ... z）。")


def find_time_col_nearby(raw: pd.DataFrame, start_row: int):
    """
    从 xyz 表头行往上找最近的 't'，返回列号
    """
    max_scan_cols = min(50, raw.shape[1])
    for r in range(start_row, max(-1, start_row - 30), -1):
        for c in range(max_scan_cols):
            v = norm(raw.iat[r, c])
            if v and T_CELL_PAT.match(v):
                return c
    raise ValueError("在 xyz 表头行上方未找到 't'，无法确定时间列。")


def extract_one_excel(xls_path: str, sheet_name=0) -> pd.DataFrame:
    raw = pd.read_excel(xls_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    meta = find_meta(raw)
    first_row = meta["first_row"]          # 例如 15（Excel行号，通常从1开始）
    data_rows_expected = meta["data_rows"] # 例如 1047576
    data_cols_expected = meta["data_cols"] # 例如 3（xyz）

    xyz_row, c_x, c_y, c_z = find_xyz_header_row(raw)
    c_t = find_time_col_nearby(raw, xyz_row)

    # 以 meta 的 first_row 为准：转成 DataFrame 的 0-based index
    data_start = first_row - 1  # 如果 first_row=15，则iloc从14开始
    if data_start < 0 or data_start >= len(raw):
        raise ValueError(f"first_row={first_row} 不在表格有效范围内。")

    # 读取 data_rows_expected 行（允许实际不足）
    data_end = min(len(raw), data_start + data_rows_expected)

    df = raw.iloc[data_start:data_end, [c_t, c_x, c_y, c_z]].copy()
    df.columns = ["time", "ax", "ay", "az"]

    # 基础清理
    df = df.dropna(how="all")
    df = df[df["time"].apply(is_number)]

    for col in ["time", "ax", "ay", "az"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time", "ax", "ay", "az"]).reset_index(drop=True)

    # 校验：xyz 列数
    if data_cols_expected != 3:
        raise ValueError(f"Data cols 期望为3（xyz），但读到 meta: {data_cols_expected}")

    # 校验：行数（允许略少，比如尾部有空行/被过滤）
    # 这里给一个较宽松的阈值：至少达到期望的 95%
    if len(df) < int(0.95 * data_rows_expected):
        raise ValueError(f"数据行数不足：期望≈{data_rows_expected}，实际={len(df)}（过滤后）")

    return df


def convert_dir(src_dir: str, label: str):
    out_dir = os.path.join(OUT_ROOT, label)
    os.makedirs(out_dir, exist_ok=True)

    excel_files = []
    for root, _, files in os.walk(src_dir):
        for fn in files:
            if fn.lower().endswith((".xlsx", ".xls")):
                excel_files.append(os.path.join(root, fn))

    print(f"[{label}] files={len(excel_files)}")

    for path in excel_files:
        base = os.path.splitext(os.path.basename(path))[0]
        out_csv = os.path.join(out_dir, base + ".csv")
        if os.path.exists(out_csv):
            print(f"  SKIP {os.path.basename(path)} -> {out_csv} 已存在")
            continue
        try:
            df = extract_one_excel(path, sheet_name=0)
            df.to_csv(out_csv, index=False, encoding="utf-8-sig")
            print(f"  OK  {os.path.basename(path)} rows={len(df)} -> {out_csv}")
        except Exception as e:
            print(f"  FAIL {os.path.basename(path)}: {e}")


def main():
    # convert_dir(OK_DIR, "OK")
    convert_dir(NG_DIR, "NG")
    print("完成")


if __name__ == "__main__":
    main()