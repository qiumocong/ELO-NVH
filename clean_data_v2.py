import os
import shutil
import pandas as pd
import torchaudio
import concurrent.futures
from pathlib import Path
from tqdm import tqdm

# ================= 配置区域 =================

# 1. 原始数据根目录 (包含 NG/OK 文件夹的地方)
SOURCE_ROOT = Path("/media/qmc/新加卷/DATA_Processed_All")

# 2. 【新】清洗后数据存放的根目录 (脚本会自动创建)
TARGET_ROOT = Path("/media/qmc/新加卷/DATA_Cleaned_Final")

# 3. 原始标签文件路径
SOURCE_CSV_PATH = SOURCE_ROOT / "labels.csv"

# 4. 新标签文件保存路径 (建议保存在新目录下)
TARGET_CSV_PATH = TARGET_ROOT / "labels.csv"

# 5. 过滤标准：帧数范围
MIN_FRAMES = 90000
MAX_FRAMES = 120000

REQUIRED_FILES = ['CW_X.wav', 'CW_Z.wav', 'CCW_X.wav', 'CCW_Z.wav']
# ===========================================

def get_audio_info(file_path):
    """获取长度、采样率和通道数"""
    try:
        metadata = torchaudio.info(str(file_path))
        return metadata.num_frames, metadata.sample_rate, metadata.num_channels
    except Exception:
        return 0, 0, 0

def analyze_folder(row_data):
    """
    只负责分析，不进行文件操作
    """
    index, row = row_data
    # 构建源路径
    source_folder = SOURCE_ROOT / row['label'] / row['folder_name']
    
    if not source_folder.exists():
        return index, "missing_folder", {}, None

    file_stats = {}
    
    # 1. 检查文件齐全性 & 获取元数据
    for fname in REQUIRED_FILES:
        fpath = source_folder / fname
        if not fpath.exists():
            return index, "missing_files", {}, None
        
        num_frames, sr, num_channels = get_audio_info(fpath)
        
        if num_frames == 0:
            return index, "corrupt_file", {}, None
        
        file_stats[fname] = {
            'len': num_frames, 
            'sr': sr, 
            'ch': num_channels
        }

    # 2. 检查 CW 和 CCW 长度范围
    cw_len = file_stats['CW_X.wav']['len']
    ccw_len = file_stats['CCW_X.wav']['len']

    if not (MIN_FRAMES <= cw_len <= MAX_FRAMES):
        return index, f"CW_len_out_{cw_len}", {}, None
    
    if not (MIN_FRAMES <= ccw_len <= MAX_FRAMES):
        return index, f"CCW_len_out_{ccw_len}", {}, None

    # 验证通过，返回源路径以便后续复制
    return index, "valid", file_stats, source_folder

def copy_worker(task):
    """
    负责复制文件的线程函数
    """
    source_folder, target_folder = task
    try:
        shutil.copytree(source_folder, target_folder, dirs_exist_ok=True)
        return True
    except Exception as e:
        print(f"复制失败: {source_folder} -> {e}")
        return False

def main():
    # 0. 初始化
    if not SOURCE_CSV_PATH.exists():
        print(f"错误: 找不到原始标签文件 {SOURCE_CSV_PATH}")
        return

    # 创建目标目录结构
    if not TARGET_ROOT.exists():
        TARGET_ROOT.mkdir(parents=True)
    (TARGET_ROOT / "NG").mkdir(exist_ok=True)
    (TARGET_ROOT / "OK").mkdir(exist_ok=True)

    print(f"源目录: {SOURCE_ROOT}")
    print(f"新目录: {TARGET_ROOT}")
    print(f"过滤范围: {MIN_FRAMES} - {MAX_FRAMES} frames")
    
    df = pd.read_csv(SOURCE_CSV_PATH)
    total_samples = len(df)
    
    # ================= 第一阶段：扫描与验证 =================
    print(f"\n[Phase 1/2] 正在扫描 {total_samples} 个样本...")
    
    tasks = [(idx, row) for idx, row in df.iterrows()]
    valid_entries = [] # 存储通过验证的数据信息
    invalid_count = 0
    
    # 使用多线程加速元数据读取
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(analyze_folder, task): task[0] for task in tasks}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=total_samples, desc="Scanning"):
            idx, status, stats, src_path = future.result()
            
            if status == "valid":
                # 保存需要的信息
                valid_entries.append({
                    "idx": idx,
                    "stats": stats,
                    "src_path": src_path
                })
            else:
                invalid_count += 1

    print(f"扫描完成。有效样本: {len(valid_entries)}，无效样本: {invalid_count}")

    # ================= 第二阶段：文件复制 =================
    print(f"\n[Phase 2/2] 正在将有效数据复制到新目录...")
    
    copy_tasks = []
    final_records = []
    
    # 准备复制任务列表和新的数据行
    for entry in valid_entries:
        idx = entry['idx']
        stats = entry['stats']
        src_path = entry['src_path']
        
        # 获取原始行信息
        original_row = df.iloc[idx]
        label = original_row['label']
        folder_name = original_row['folder_name']
        
        # 构建目标路径: TARGET_ROOT / NG / folder_name
        target_path = TARGET_ROOT / label / folder_name
        
        # 添加到复制队列
        copy_tasks.append((src_path, target_path))
        
        # 准备新 CSV 的一行数据 (保留原始所有列，追加新列)
        new_row = original_row.to_dict()
        
        # 追加详细元数据
        new_row['len_cw'] = stats['CW_X.wav']['len']
        new_row['sr_cw'] = stats['CW_X.wav']['sr']
        new_row['ch_cw'] = stats['CW_X.wav']['ch']
        
        new_row['len_ccw'] = stats['CCW_X.wav']['len']
        new_row['sr_ccw'] = stats['CCW_X.wav']['sr']
        new_row['ch_ccw'] = stats['CCW_X.wav']['ch']
        
        # 更新 original_path 为新路径 (可选，看你是否需要指向新位置)
        new_row['original_path'] = str(target_path)
        
        final_records.append(new_row)

    # 执行复制 (使用多线程加速 IO，如果是机械硬盘建议 workers=4，固态硬盘可以 16)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(copy_worker, task) for task in copy_tasks]
        
        # 等待所有复制完成
        for _ in tqdm(concurrent.futures.as_completed(futures), total=len(copy_tasks), desc="Copying"):
            pass

    # ================= 第三阶段：生成新 CSV =================
    print("\n正在生成新的标签文件...")
    df_clean = pd.DataFrame(final_records)
    
    # 确保列顺序美观（把新列放后面）
    cols = list(df.columns)
    new_cols = ['len_cw', 'sr_cw', 'ch_cw', 'len_ccw', 'sr_ccw', 'ch_ccw']
    # 移除 cols 里可能已存在的重复列名，防止报错
    cols = [c for c in cols if c not in new_cols]
    final_cols = cols + new_cols
    
    df_clean = df_clean[final_cols]
    df_clean.to_csv(TARGET_CSV_PATH, index=False, encoding='utf-8-sig')

    # ================= 报告 =================
    if len(df_clean) > 0:
        max_cw = df_clean['len_cw'].max()
        max_ccw = df_clean['len_ccw'].max()
    else:
        max_cw = 0
        max_ccw = 0

    print("\n" + "="*40)
    print("MIGRATION REPORT (迁移报告)")
    print("="*40)
    print(f"原始数据总量 : {total_samples}")
    print(f"符合要求并迁移: {len(df_clean)}")
    print(f"被过滤/丢弃  : {invalid_count}")
    print("-" * 40)
    print(f"新数据存放位置: {TARGET_ROOT}")
    print(f"新 CSV 文件   : {TARGET_CSV_PATH}")
    print("-" * 40)
    print(f"新数据集最大 CW 长度 : {max_cw}")
    print(f"新数据集最大 CCW 长度: {max_ccw}")
    print("\n接下来请修改 config.py:")
    print(f'1. CSV_PATH = "{TARGET_CSV_PATH}"')
    print(f"2. LEN_CW   = {int(max_cw * 1.02)}")
    print(f"3. LEN_CCW  = {int(max_ccw * 1.02)}")

if __name__ == "__main__":
    main()