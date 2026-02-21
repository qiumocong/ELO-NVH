import os
import shutil
import csv
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ================= 配置区域 =================

# 1. 源数据根目录
SOURCE_ROOT = Path("./DATA")

# 2. 输出数据目录
TARGET_ROOT = Path("./DATA_Processed_All")

# 3. 标签文件保存路径
LABEL_FILE = TARGET_ROOT / "labels.csv"

# 4. 模式选择 (True=复制, False=移动)
COPY_MODE = True 

# 5. 线程数量
# 如果是机械硬盘(HDD)，建议设为 4-8，设太大反而会因为磁头寻道变慢
# 如果是固态硬盘(SSD)，可以设为 8-16
MAX_WORKERS = 4

# ===========================================

# 全局锁，用于多线程写入 csv 数据时的安全
data_lock = threading.Lock()

def scan_tasks(source_dir, target_root_name):
    """
    第一阶段：只扫描，不复制。快速生成任务列表。
    """
    tasks = []
    print("正在扫描目录结构，生成任务列表...")
    
    if not source_dir.exists():
        return []

    # 遍历年份
    for year_folder in source_dir.iterdir():
        if not year_folder.is_dir() or year_folder.name == target_root_name:
            continue

        # 遍历日期
        for day_folder in year_folder.iterdir():
            if not day_folder.is_dir():
                continue

            # 遍历 NG/OK
            for label_type in ["NG", "OK"]:
                category_path = day_folder / label_type
                if not category_path.exists():
                    continue

                # 遍历样本
                for sample_folder in category_path.iterdir():
                    if not sample_folder.is_dir():
                        continue
                    
                    # 遍历视角 (这是最小任务单元)
                    for view_folder in sample_folder.iterdir():
                        if not view_folder.is_dir():
                            continue

                        # 准备任务数据
                        raw_name = f"{sample_folder.name}_{view_folder.name}"
                        clean_name = raw_name.replace(" ", "") # 去空格
                        
                        tasks.append({
                            "src_path": view_folder,
                            "clean_name": clean_name,
                            "label": label_type,
                            "year": year_folder.name,
                            "date": day_folder.name
                        })
    return tasks

def scan_tasks_new(source_dir, target_root_name):
    tasks = []
    print("正在扫描目录结构，生成任务列表...")

    if not source_dir.exists():
        return []

    for category_path in source_dir.iterdir():
        label_type = os.path.basename(category_path)
    # # 遍历 NG/OK
    # for label_type in ["NG", "OK"]:
    #     category_path = day_folder / label_type
    #     if not category_path.exists():
    #         continue

        # 遍历样本
        for sample_folder in category_path.iterdir():
            if not sample_folder.is_dir():
                continue

            # 遍历视角 (这是最小任务单元)
            for view_folder in sample_folder.iterdir():
                if not view_folder.is_dir():
                    continue

                # 准备任务数据
                raw_name = f"{sample_folder.name}_{view_folder.name}"
                clean_name = raw_name.replace(" ", "")  # 去空格

                tasks.append({
                    "src_path": view_folder,
                    "clean_name": clean_name,
                    "label": label_type,
                    "year": "None",
                    "date": "None"
                })
    return tasks

def process_single_task(task):
    """
    第二阶段：工作线程执行的具体函数
    """
    try:
        # 构建目标路径
        if task["label"] == "NG":
            dest_parent = TARGET_ROOT / "NG"
        else:
            dest_parent = TARGET_ROOT / "OK"
            
        dest_path = dest_parent / task["clean_name"]
        
        # 执行文件操作 (IO 密集型操作)
        if COPY_MODE:
            shutil.copytree(task["src_path"], dest_path, dirs_exist_ok=True)
        else:
            shutil.move(str(task["src_path"]), str(dest_path))
            
        # 返回成功结果
        return {
            "status": "success",
            "data": {
                "folder_name": task["clean_name"],
                "label": task["label"],
                "label_id": 1 if task["label"] == "NG" else 0,
                "original_path": str(task["src_path"]),
                "year": task["year"],
                "date": task["date"]
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "msg": f"{task['src_path']} -> {e}"
        }

def main():
    # 1. 初始化目录
    ng_target_dir = TARGET_ROOT / "NG"
    ok_target_dir = TARGET_ROOT / "OK"
    ng_target_dir.mkdir(parents=True, exist_ok=True)
    ok_target_dir.mkdir(parents=True, exist_ok=True)

    print(f"源目录: {SOURCE_ROOT}")
    print(f"目标目录: {TARGET_ROOT}")
    print(f"启用线程数: {MAX_WORKERS}")

    # 2. 获取所有任务
    # all_tasks = scan_tasks(SOURCE_ROOT, TARGET_ROOT.name)
    all_tasks = scan_tasks_new(SOURCE_ROOT, TARGET_ROOT.name)
    total_count = len(all_tasks)
    print(f"扫描完成，共发现 {total_count} 个待处理文件夹。")
    print("-" * 30)

    results_data = []
    stats = {"NG": 0, "OK": 0}

    # 3. 建立线程池并行处理
    # 使用 ThreadPoolExecutor 管理线程
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        # future_to_task 字典用于追踪每个 future 对应的任务（可选，用于调试）
        futures = [executor.submit(process_single_task, task) for task in all_tasks]
        
        # 使用 tqdm 显示进度，as_completed 会在某个线程完成时立即 yield
        with tqdm(total=total_count, unit="folder", desc="多线程处理中") as pbar:
            for future in as_completed(futures):
                result = future.result()
                
                if result["status"] == "success":
                    # 收集数据
                    item = result["data"]
                    results_data.append(item)
                    
                    # 更新统计 (这里在主线程运行，不需要锁)
                    stats[item["label"]] += 1
                    
                    # 更新进度条后缀
                    pbar.set_postfix(file=item["folder_name"][-15:])
                else:
                    # 打印错误信息
                    tqdm.write(f"错误: {result['msg']}")
                
                pbar.update(1)

    # 4. 生成 CSV 文件
    print("\n正在写入标签文件...")
    with open(LABEL_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        fieldnames = ["folder_name", "label", "label_id", "original_path", "year", "date"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_data)

    print("="*30)
    print("多线程处理完成！")
    print(f"总计 NG: {stats['NG']}")
    print(f"总计 OK: {stats['OK']}")
    print(f"输出目录: {TARGET_ROOT}")
    print("="*30)

if __name__ == "__main__":
    main()