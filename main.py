import os
import torch
import torch.nn as nn
import torch.optim as optim
import torchaudio
import pandas as pd
import numpy as np
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler, Subset
from sklearn.model_selection import train_test_split
from tqdm import tqdm
from sklearn.metrics import confusion_matrix, classification_report

# ================= 1. 全局配置 (Configuration) =================

CONFIG = {
    # 路径配置
    "CSV_PATH": "./DATA_Processed_All/labels.csv",
    "SAVE_DIR": "./logs",
    
    # 音频参数 (根据 soxi 结果)
    "SAMPLE_RATE": 22050,
    # 设定长度 (根据之前的统计结果，留有余量)
    "LEN_CW": 200000,   # 约 5秒
    "LEN_CCW": 200000,  # 约 6.8秒
    # 总输入长度 = CW + CCW
    "TOTAL_LEN": 400000,
    
    # 训练超参数
    "BATCH_SIZE": 8,
    "EPOCHS": 30,
    "LR": 0.001,
    "NUM_WORKERS": 8,   # 根据CPU核心数调整
    "DEVICE": torch.device("cuda" if torch.cuda.is_available() else "cpu")
}

# 创建保存目录
os.makedirs(CONFIG["SAVE_DIR"], exist_ok=True)

# ================= 2. 数据集定义 (Dataset) =================

class MotorFusedDataset(Dataset):
    def __init__(self, csv_file, len_cw=CONFIG["LEN_CW"], len_ccw=CONFIG["LEN_CCW"]):
        """
        读取 CSV 并定义数据处理逻辑
        """
        self.annotations = pd.read_csv(csv_file)
        self.len_cw = len_cw
        self.len_ccw = len_ccw
        
    def __len__(self):
        return len(self.annotations)
    
    def _load_process_pad(self, path, target_len):
        """
        辅助函数：
        1. 读取音频
        2. 双声道 -> 单声道 (Mean)
        3. 截断或补零到 target_len
        """
        if not os.path.exists(path):
            # 如果文件缺失，返回全0张量
            return torch.zeros(1, target_len)
            
        try:
            # 读取音频 (Shape: [Channels, Time])
            # torchaudio 加载后通常是 float32
            wf, sr = torchaudio.load(path)
            
            # 【关键】双声道转单声道 (2, T) -> (1, T)
            wf = torch.mean(wf, dim=0, keepdim=True)
            
            current_len = wf.shape[1]
            if current_len > target_len:
                # 截断
                return wf[:, :target_len]
            else:
                # 补零 (右侧填充)
                padding = target_len - current_len
                return torch.nn.functional.pad(wf, (0, padding))
        except Exception as e:
            # print(f"Error reading {path}: {e}")
            return torch.zeros(1, target_len)

    def __getitem__(self, index):
        folder_path = self.annotations.iloc[index, 3] # 'original_path' 列
        label = int(self.annotations.iloc[index, 2])  # 'label_id' 列 (NG=1, OK=0)

        # --- 1. 处理 X 轴 (CW + CCW) ---
        # 拼接策略：先各自对齐，再拼接。保证 CCW 永远在固定位置开始。
        cw_x = self._load_process_pad(os.path.join(folder_path, 'CW_X.wav'), self.len_cw)
        ccw_x = self._load_process_pad(os.path.join(folder_path, 'CCW_X.wav'), self.len_ccw)
        full_x = torch.cat([cw_x, ccw_x], dim=1) # Dim 1 是时间轴

        # --- 2. 处理 Z 轴 (CW + CCW) ---
        cw_z = self._load_process_pad(os.path.join(folder_path, 'CW_Z.wav'), self.len_cw)
        ccw_z = self._load_process_pad(os.path.join(folder_path, 'CCW_Z.wav'), self.len_ccw)
        full_z = torch.cat([cw_z, ccw_z], dim=1)

        # --- 3. 堆叠 X 和 Z ---
        # 最终 Shape: (2, 260000) -> [通道数, 时间长度]
        input_tensor = torch.cat([full_x, full_z], dim=0)

        return input_tensor, torch.tensor(label, dtype=torch.long)

# ================= 3. 模型定义 (1D-CNN) =================

class FusedMotorClassifier(nn.Module):
    def __init__(self, input_channels=2, num_classes=2):
        super(FusedMotorClassifier, self).__init__()
        
        # 特征提取器
        self.features = nn.Sequential(
            # 输入: (B, 2, 260000)
            # Layer 1: 大步长快速降维
            nn.Conv1d(input_channels, 16, kernel_size=64, stride=4, padding=30),
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.MaxPool1d(4), 
            
            # Layer 2
            nn.Conv1d(16, 32, kernel_size=32, stride=2, padding=15),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(4),
            
            # Layer 3
            nn.Conv1d(32, 64, kernel_size=16, stride=2, padding=7),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(4),
            
            # Layer 4
            nn.Conv1d(64, 128, kernel_size=8, stride=1, padding=3),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            
            # Global Average Pooling
            # 将任意长度的时间轴压缩为 1 个点: (B, 128, T) -> (B, 128, 1)
            nn.AdaptiveAvgPool1d(1) 
        )
        
        # 分类头
        self.classifier = nn.Sequential(
            nn.Flatten(), # (B, 128)
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.5), # 防止过拟合
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x

# ================= 4. 数据加载与分割 (Data Loading) =================

def get_dataloaders():
    print("正在初始化数据集并进行分层切分...")
    
    # 1. 读取索引和标签用于切分
    df = pd.read_csv(CONFIG["CSV_PATH"])
    indices = list(range(len(df)))
    labels = df['label_id'].values
    
    # 2. 分层切分 (70% Train, 15% Val, 15% Test)
    train_idx, temp_idx, train_labels, temp_labels = train_test_split(
        indices, labels, test_size=0.3, stratify=labels, random_state=42
    )
    val_idx, test_idx, val_labels, test_labels = train_test_split(
        temp_idx, temp_labels, test_size=0.5, stratify=temp_labels, random_state=42
    )
    
    print(f"训练集: {len(train_idx)} | 验证集: {len(val_idx)} | 测试集: {len(test_idx)}")

    # 3. 计算训练集采样权重 (解决不平衡)
    count_ng = np.sum(train_labels == 1)
    count_ok = np.sum(train_labels == 0)
    weight_ng = 1.0 / count_ng
    weight_ok = 1.0 / count_ok
    
    # 为训练集每个样本分配权重
    samples_weights = torch.tensor([weight_ng if t == 1 else weight_ok for t in train_labels], dtype=torch.double)
    
    # 创建采样器
    sampler = WeightedRandomSampler(samples_weights, len(samples_weights), replacement=True)
    
    # 4. 初始化完整 Dataset
    full_dataset = MotorFusedDataset(CONFIG["CSV_PATH"])
    
    # 5. 创建 DataLoader
    train_loader = DataLoader(
        Subset(full_dataset, train_idx),
        batch_size=CONFIG["BATCH_SIZE"],
        sampler=sampler,      # 这里的关键：使用采样器
        shuffle=False,        # sampler 和 shuffle 互斥
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

# ================= 5. 训练与验证逻辑 =================

def evaluate(model, loader, device, phase="Validation"):
    model.eval()
    all_preds = []
    all_labels = []
    running_loss = 0.0
    criterion = nn.CrossEntropyLoss()
    
    with torch.no_grad():
        for inputs, labels in loader:
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            running_loss += loss.item()
            
            _, preds = torch.max(outputs, 1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            
    avg_loss = running_loss / len(loader)
    
    # 打印详细报告 (包含 Precision, Recall, F1)
    print(f"\n--- {phase} Report ---")
    print(f"Loss: {avg_loss:.4f}")
    # digits=4 保证我们能看到小数点后4位，这对于不平衡数据很重要
    print(classification_report(all_labels, all_preds, target_names=['OK', 'NG'], digits=4))
    
    # 返回 NG 类别的 Recall (召回率) 作为关键指标保存最佳模型
    # target_names[1] 是 NG
    report_dict = classification_report(all_labels, all_preds, output_dict=True)
    ng_recall = report_dict['1']['recall']
    
    return avg_loss, ng_recall

def train_model():
    # 获取数据
    train_loader, val_loader, test_loader = get_dataloaders()
    
    # 初始化模型
    model = FusedMotorClassifier().to(CONFIG["DEVICE"])
    print(f"模型初始化完成，运行在: {CONFIG['DEVICE']}")
    
    # 定义损失函数和优化器
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=CONFIG["LR"])
    
    best_ng_recall = 0.0
    
    for epoch in range(CONFIG["EPOCHS"]):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        
        print(f"\nEpoch {epoch+1}/{CONFIG['EPOCHS']}")
        # 训练循环
        pbar = tqdm(train_loader, total=len(train_loader), desc="Training")
        
        for inputs, labels in pbar:
            inputs, labels = inputs.to(CONFIG["DEVICE"]), labels.to(CONFIG["DEVICE"])
            
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
            
            pbar.set_postfix({'loss': f'{loss.item():.4f}', 'acc': f'{100*correct/total:.2f}%'})
            
        # 每个 Epoch 结束后验证
        val_loss, val_ng_recall = evaluate(model, val_loader, CONFIG["DEVICE"], phase="Validation")
        
        # 保存最佳模型 (以 NG 检出率/Recall 为标准)
        if val_ng_recall > best_ng_recall:
            best_ng_recall = val_ng_recall
            save_path = os.path.join(CONFIG["SAVE_DIR"], "best_model.pth")
            torch.save(model.state_dict(), save_path)
            print(f"🌟 新的最佳模型已保存! NG Recall: {best_ng_recall:.4f}")
            
    print("\n训练结束，正在进行最终测试集评估...")
    
    # 加载最佳权重进行测试
    model.load_state_dict(torch.load(os.path.join(CONFIG["SAVE_DIR"], "best_model.pth")))
    evaluate(model, test_loader, CONFIG["DEVICE"], phase="Final Test")

if __name__ == "__main__":
    train_model()