import os
import shutil
import pandas as pd
import torchaudio
import concurrent.futures
from pathlib import Path
from tqdm import tqdm

# ================= 配置区域 =================
# 数据集根目录 (处理后的数据目录)
DATA_ROOT = Path("/media/qmc/新加卷/DATA_Processed_All")
# 标签文件路径
CSV_PATH = DATA_ROOT / "labels.csv"
# 清洗后的标签文件保存路径
CLEANED_CSV_PATH = DATA_ROOT / "labels_cleaned.csv"

# 必须存在的4个文件
REQUIRED_FILES = ['CW_X.wav', 'CW_Z.wav', 'CCW_X.wav', 'CCW_Z.wav']
# ===========================================

def get_audio_len(file_path):
    """只读取元数据获取长度，不加载音频，速度极快"""
    try:
        metadata = torchaudio.info(str(file_path))
        return metadata.num_frames
    except Exception:
        return 0

def process_row(row_data):
    """处理单行数据的函数，用于多线程"""
    index, row = row_data
    
    # 构建实际的文件夹路径: DATA_ROOT / NG / folder_name
    # 注意：这里我们信任 CSV 的 label 列来定位文件夹
    folder_path = DATA_ROOT / row['label'] / row['folder_name']
    
    # 1. 检查文件夹是否存在
    if not folder_path.exists():
        return index, "missing_folder", 0, 0, None

    # 2. 检查4个文件是否齐全
    for fname in REQUIRED_FILES:
        if not (folder_path / fname).exists():
            return index, "missing_files", 0, 0, folder_path

    # 3. 如果齐全，获取 CW_X 和 CCW_X 的长度
    # 我们只关心 X 轴长度，因为 Z 轴通常是同步录制的，长度一致
    len_cw = get_audio_len(folder_path / 'CW_X.wav')
    len_ccw = get_audio_len(folder_path / 'CCW_X.wav')

    # 再次检查：如果文件存在但长度为0（损坏的文件），也视为无效
    if len_cw == 0 or len_ccw == 0:
        return index, "corrupt_files", 0, 0, folder_path

    return index, "valid", len_cw, len_ccw, None

def main():
    print(f"正在读取标签文件: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    original_count = len(df)
    
    print(f"总数据量: {original_count}")
    print("开始扫描与清洗 (这可能需要几分钟)...")

    # 准备任务
    tasks = [(idx, row) for idx, row in df.iterrows()]
    
    valid_indices = []
    cw_lengths = []
    ccw_lengths = []
    deleted_folders = 0
    
    # 结果存储字典，用于按索引回填
    results = {}

    # 使用多线程加速 IO 操作
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(process_row, task): task[0] for task in tasks}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(tasks), desc="Processing"):
            idx, status, len_cw, len_ccw, path_to_delete = future.result()
            results[idx] = (status, len_cw, len_ccw)
            
            # 如果判定为无效，执行物理删除
            if status in ["missing_files", "corrupt_files"] and path_to_delete:
                try:
                    # 递归删除文件夹
                    shutil.rmtree(path_to_delete)
                    # print(f"已删除无效数据: {path_to_delete}") # 如果想看刷屏可以取消注释
                    deleted_folders += 1
                except Exception as e:
                    print(f"删除失败 {path_to_delete}: {e}")

    # --- 整理数据 ---
    print("\n正在更新 DataFrame...")
    
    # 按照原始 DataFrame 的顺序重组数据
    keep_mask = []
    list_len_cw = []
    list_len_ccw = []
    
    for idx in df.index:
        status, len_cw, len_ccw = results[idx]
        if status == "valid":
            keep_mask.append(True)
            list_len_cw.append(len_cw)
            list_len_ccw.append(len_ccw)
        else:
            keep_mask.append(False)

    # 筛选有效行
    df_clean = df[keep_mask].copy()
    
    # 添加新列
    df_clean['len_cw'] = list_len_cw
    df_clean['len_ccw'] = list_len_ccw

    # 保存新的 CSV
    df_clean.to_csv(CLEANED_CSV_PATH, index=False, encoding='utf-8-sig')

    # --- 统计报告 ---
    max_cw = df_clean['len_cw'].max()
    max_ccw = df_clean['len_ccw'].max()
    
    print("=" * 40)
    print("清洗完成报告")
    print("=" * 40)
    print(f"原始数量: {original_count}")
    print(f"剩余数量: {len(df_clean)}")
    print(f"已删除/无效数量: {original_count - len(df_clean)}")
    print(f"物理删除文件夹数: {deleted_folders}")
    print("-" * 40)
    print(f"CW_X 最大长度:  {max_cw} (约 {max_cw/22050:.2f} 秒)")
    print(f"CCW_X 最大长度: {max_ccw} (约 {max_ccw/22050:.2f} 秒)")
    print("-" * 40)
    print(f"新的标签文件已保存至: {CLEANED_CSV_PATH}")
    print("\n*** 请根据以上最大长度更新 main.py 中的 CONFIG ***")
    print(f"建议设置 LEN_CW  = {int(max_cw * 1.02)}") # 留2%余量
    print(f"建议设置 LEN_CCW = {int(max_ccw * 1.02)}")

if __name__ == "__main__":
    # 二次确认，防止误删
    print(f"警告: 此脚本将【永久删除】 {DATA_ROOT} 下不完整的数据文件夹。")
    x = input("输入 'yes' 继续，其他键退出: ")
    if x.lower() == 'yes':
        main()
    else:
        print("已取消。")