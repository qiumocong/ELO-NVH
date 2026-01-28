# dataset.py

import os
import torch
import torchaudio
import pandas as pd
import numpy as np
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler, Subset
from sklearn.model_selection import train_test_split
from config import CONFIG

class MotorFusedDataset(Dataset):
    def __init__(self, data_source, len_cw=CONFIG["LEN_CW"], len_ccw=CONFIG["LEN_CCW"]):
        """
        data_source: 可以是 csv 文件路径(str)，也可以是 pandas DataFrame
        """
        # === 修改点 1: 支持 DataFrame 输入 ===
        if isinstance(data_source, str):
            self.annotations = pd.read_csv(data_source)
        elif isinstance(data_source, pd.DataFrame):
            self.annotations = data_source
        else:
            raise ValueError("data_source must be a file path or a DataFrame")
            
        self.len_cw = len_cw
        self.len_ccw = len_ccw
        
    def __len__(self):
        return len(self.annotations)
    
    def _load_process_pad(self, path, target_len):
        # ... (这部分代码保持不变) ...
        if not os.path.exists(path):
            return torch.zeros(1, target_len)
        try:
            wf, sr = torchaudio.load(path)
            wf = torch.mean(wf, dim=0, keepdim=True)
            current_len = wf.shape[1]
            if current_len > target_len:
                return wf[:, :target_len]
            else:
                padding = target_len - current_len
                return torch.nn.functional.pad(wf, (0, padding))
        except Exception:
            return torch.zeros(1, target_len)

    def __getitem__(self, index):
        # ... (这部分代码保持不变) ...
        folder_path = self.annotations.iloc[index, 3] 
        label = int(self.annotations.iloc[index, 2])
        
        cw_x = self._load_process_pad(os.path.join(folder_path, 'CW_X.wav'), self.len_cw)
        ccw_x = self._load_process_pad(os.path.join(folder_path, 'CCW_X.wav'), self.len_ccw)
        full_x = torch.cat([cw_x, ccw_x], dim=1)

        cw_z = self._load_process_pad(os.path.join(folder_path, 'CW_Z.wav'), self.len_cw)
        ccw_z = self._load_process_pad(os.path.join(folder_path, 'CCW_Z.wav'), self.len_ccw)
        full_z = torch.cat([cw_z, ccw_z], dim=1)

        input_tensor = torch.cat([full_x, full_z], dim=0)
        return input_tensor, torch.tensor(label, dtype=torch.long)

def get_dataloaders():
    print("正在初始化数据集...")
    
    # 1. 读取原始 CSV
    df = pd.read_csv(CONFIG["CSV_PATH"])
    
    # === 修改点: 严格分层采样 (Stratified Sampling) ===
    if CONFIG.get("MAX_SAMPLES") is not None:
        if len(df) > CONFIG["MAX_SAMPLES"]:
            print(f"🐞 Debug模式: 正在进行分层采样，抽取 {CONFIG['MAX_SAMPLES']} 条数据...")
            
            # 使用 train_test_split 来做“截取”，利用 stratify 参数保持比例
            # 我们只需要 "train" 部分作为我们的子数据集，"test" 部分丢弃
            df_subset, _ = train_test_split(
                df, 
                train_size=CONFIG["MAX_SAMPLES"], 
                stratify=df['label_id'], # <--- 关键：保证 NG/OK 比例不变
                random_state=42
            )
            
            # 重置索引，防止 Dataset 报错
            df = df_subset.reset_index(drop=True)
            
            # 打印一下当前的比例，让你放心
            ng_cnt = sum(df['label_id'] == 1)
            ok_cnt = sum(df['label_id'] == 0)
            print(f"   -> 抽取结果: NG={ng_cnt}, OK={ok_cnt} (比例约为 1:{ok_cnt/ng_cnt:.1f})")
        else:
            print(f"数据量小于 {CONFIG['MAX_SAMPLES']}，使用全部数据。")
            
    # 2. 准备切分数据 (基于截取后的 df)
    indices = list(range(len(df)))
    labels = df['label_id'].values
    
    print("正在进行分层切分...")
    # 这里的 stratify 保证了即使是 1000 条，NG/OK 的比例也和原来一样
    train_idx, temp_idx, train_labels, temp_labels = train_test_split(
        indices, labels, test_size=0.3, stratify=labels, random_state=42
    )
    val_idx, test_idx, val_labels, test_labels = train_test_split(
        temp_idx, temp_labels, test_size=0.5, stratify=temp_labels, random_state=42
    )
    
    print(f"训练集: {len(train_idx)} | 验证集: {len(val_idx)} | 测试集: {len(test_idx)}")

    # 3. 计算加权采样器
    count_ng = np.sum(train_labels == 1)
    count_ok = np.sum(train_labels == 0)
    # 防止分母为0 (极小样本时可能发生)
    count_ng = max(count_ng, 1) 
    count_ok = max(count_ok, 1)
    
    weight_ng = 1.0 / count_ng
    weight_ok = 1.0 / count_ok
    
    samples_weights = torch.tensor([weight_ng if t == 1 else weight_ok for t in train_labels], dtype=torch.double)
    sampler = WeightedRandomSampler(samples_weights, len(samples_weights), replacement=True)
    
    # 4. 初始化 Dataset (传入处理过的 df 而不是路径)
    full_dataset = MotorFusedDataset(df)
    
    # 5. 构建 DataLoaders (保持不变)
    train_loader = DataLoader(
        Subset(full_dataset, train_idx),
        batch_size=CONFIG["BATCH_SIZE"],
        sampler=sampler,
        shuffle=False, 
        num_workers=CONFIG["NUM_WORKERS"],
        pin_memory=True
    )
    
    val_loader = DataLoader(
        Subset(full_dataset, val_idx),
        batch_size=CONFIG["BATCH_SIZE"],
        shuffle=False,
        num_workers=CONFIG["NUM_WORKERS"],
        pin_memory=True
    )
    
    test_loader = DataLoader(
        Subset(full_dataset, test_idx),
        batch_size=CONFIG["BATCH_SIZE"],
        shuffle=False,
        num_workers=CONFIG["NUM_WORKERS"],
        pin_memory=True
    )
    
    return train_loader, val_loader, test_loader