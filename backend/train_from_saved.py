import os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix
from tqdm import tqdm
import re
from model import Accel1DCNN
from config import DATA_SAVE_DIR, MODEL_DIR, DEVICE, MODEL_IN_CH, MODEL_NUM_CLASSES, TRAIN_CONFIG, OK_DIRNAME, NG_DIRNAME

# ---------- 数据集 ----------
class VibrationDataset(Dataset):
    def __init__(self, data_dir, spec_name, input_indices=[0,1], max_len=None):
        self.samples = []
        self.input_indices = input_indices
        self.max_len = max_len
        for label_name in [OK_DIRNAME, NG_DIRNAME]:
            label = 0 if label_name == OK_DIRNAME else 1
            label_path = os.path.join(data_dir, label_name)
            if not os.path.isdir(label_path):
                continue
            for barcode in os.listdir(label_path):
                barcode_path = os.path.join(label_path, barcode)
                if not os.path.isdir(barcode_path):
                    continue
                spec_path = os.path.join(barcode_path, spec_name)
                if not os.path.isdir(spec_path):
                    continue
                ch_files = [f for f in os.listdir(spec_path) if f.startswith("ch") and f.endswith(".csv")]
                if not ch_files:
                    continue
                ch_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
                data_dict = {}
                max_len_sample = 0
                for ch_file in ch_files:
                    ch_idx = int(re.search(r'\d+', ch_file).group())
                    df = pd.read_csv(os.path.join(spec_path, ch_file))
                    if 'time' not in df.columns:
                        continue
                    vals = df.iloc[:, 1].values
                    if max_len_sample == 0:
                        max_len_sample = len(vals)
                    else:
                        max_len_sample = min(max_len_sample, len(vals))
                    data_dict[ch_idx] = vals
                if not data_dict:
                    continue
                n_channels = max(data_dict.keys()) + 1
                seq_len = max_len_sample
                if seq_len == 0:
                    continue
                data_matrix = np.zeros((n_channels, seq_len))
                for ch_idx, vals in data_dict.items():
                    data_matrix[ch_idx, :seq_len] = vals[:seq_len]
                if self.input_indices:
                    input_data = data_matrix[self.input_indices, :]
                else:
                    input_data = data_matrix
                if self.max_len is not None and input_data.shape[1] > self.max_len:
                    input_data = input_data[:, :self.max_len]
                self.samples.append((input_data.astype(np.float32), label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        data, label = self.samples[idx]
        return torch.from_numpy(data), label

# ---------- collate & evaluate ----------
def collate_fn(batch):
    tensors, labels = zip(*batch)
    lengths = [t.shape[1] for t in tensors]
    max_len = max(lengths)
    channels = tensors[0].shape[0]
    padded = torch.zeros((len(tensors), channels, max_len), dtype=torch.float32)
    for i, t in enumerate(tensors):
        padded[i, :, :t.shape[1]] = t
    return padded, torch.tensor(labels, dtype=torch.long), torch.tensor(lengths, dtype=torch.long)

def evaluate(model, loader, device, phase="Validation"):
    model.eval()
    criterion = nn.CrossEntropyLoss()
    all_preds, all_labels = [], []
    running_loss = 0.0
    with torch.no_grad():
        for X, y, lengths in loader:
            X = X.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            logits = model(X)
            loss = criterion(logits, y)
            running_loss += loss.item()
            preds = torch.argmax(logits, dim=1)
            all_preds.extend(preds.cpu().numpy().tolist())
            all_labels.extend(y.cpu().numpy().tolist())
    avg_loss = running_loss / max(len(loader), 1)
    print(f"\n--- {phase} Report ---")
    print(f"Loss: {avg_loss:.4f}")
    print(classification_report(all_labels, all_preds, target_names=["OK", "NG"], digits=4, zero_division=0))
    cm = confusion_matrix(all_labels, all_preds, labels=[0,1])
    print("Confusion Matrix:")
    print(cm)
    rep = classification_report(all_labels, all_preds, output_dict=True, zero_division=0)
    return avg_loss, {
        "ng_recall": rep.get("1", {}).get("recall", 0.0),
        "macro_f1": rep.get("macro avg", {}).get("f1-score", 0.0),
        "acc": rep.get("accuracy", 0.0)
    }

# ---------- 训练单个规格 ----------
def train_spec(spec_name, data_dir, model_dir):
    print(f"\n===== 训练规格: {spec_name} =====")
    dataset = VibrationDataset(data_dir, spec_name, input_indices=[0,1], max_len=TRAIN_CONFIG["max_len"])
    if len(dataset) < TRAIN_CONFIG["min_samples_per_spec"]:
        print(f"规格 {spec_name} 样本数 {len(dataset)} 低于阈值 {TRAIN_CONFIG['min_samples_per_spec']}，跳过训练")
        return

    total = len(dataset)
    test_size = int(total * TRAIN_CONFIG["test_size"])
    val_size = int(total * TRAIN_CONFIG["val_size"])
    labels = [label for _, label in dataset.samples]
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=test_size+val_size, random_state=TRAIN_CONFIG["seed"])
    train_idx, temp_idx = next(splitter.split(np.zeros(total), labels))
    temp_labels = [labels[i] for i in temp_idx]
    val_ratio = val_size / (test_size + val_size)
    splitter2 = StratifiedShuffleSplit(n_splits=1, test_size=1-val_ratio, random_state=TRAIN_CONFIG["seed"])
    val_idx, test_idx = next(splitter2.split(np.zeros(len(temp_idx)), temp_labels))
    val_idx = [temp_idx[i] for i in val_idx]
    test_idx = [temp_idx[i] for i in test_idx]

    train_dataset = torch.utils.data.Subset(dataset, train_idx)
    val_dataset = torch.utils.data.Subset(dataset, val_idx)
    test_dataset = torch.utils.data.Subset(dataset, test_idx)

    train_loader = DataLoader(train_dataset, batch_size=TRAIN_CONFIG["batch_size"],
                              shuffle=True, collate_fn=collate_fn,
                              num_workers=TRAIN_CONFIG["num_workers"],
                              pin_memory=TRAIN_CONFIG["pin_memory"])
    val_loader = DataLoader(val_dataset, batch_size=TRAIN_CONFIG["batch_size"],
                            shuffle=False, collate_fn=collate_fn,
                            num_workers=TRAIN_CONFIG["num_workers"],
                            pin_memory=TRAIN_CONFIG["pin_memory"])
    test_loader = DataLoader(test_dataset, batch_size=TRAIN_CONFIG["batch_size"],
                             shuffle=False, collate_fn=collate_fn,
                             num_workers=TRAIN_CONFIG["num_workers"],
                             pin_memory=TRAIN_CONFIG["pin_memory"])

    print(f"总样本: {len(dataset)}, 训练: {len(train_dataset)}, 验证: {len(val_dataset)}, 测试: {len(test_dataset)}")

    model = Accel1DCNN(in_ch=MODEL_IN_CH, num_classes=MODEL_NUM_CLASSES).to(DEVICE)
    optimizer = optim.AdamW(model.parameters(), lr=TRAIN_CONFIG["lr"], weight_decay=TRAIN_CONFIG["weight_decay"])
    criterion = nn.CrossEntropyLoss()
    best_val_loss = float("inf")
    model_path = os.path.join(model_dir, f"{spec_name}.pth")

    for epoch in range(TRAIN_CONFIG["epochs"]):
        model.train()
        running_loss = 0.0
        correct = 0
        total_samples = 0
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{TRAIN_CONFIG['epochs']}")
        for X, y, lengths in pbar:
            X = X.to(DEVICE, non_blocking=True)
            y = y.to(DEVICE, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            logits = model(X)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            preds = torch.argmax(logits, dim=1)
            total_samples += y.size(0)
            correct += (preds == y).sum().item()
            pbar.set_postfix(loss=f"{loss.item():.4f}", acc=f"{100.0*correct/max(total_samples,1):.2f}%")
        train_loss = running_loss / max(len(train_loader), 1)
        train_acc = correct / max(total_samples, 1)
        val_loss, val_metrics = evaluate(model, val_loader, DEVICE, phase="Validation")
        val_acc = val_metrics["acc"]
        print(f"[Epoch {epoch+1}] train_loss={train_loss:.4f} train_acc={train_acc:.4f} | val_loss={val_loss:.4f} val_acc={val_acc:.4f}")
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), model_path)
            print(f"🌟 保存模型: {model_path} (val_loss={best_val_loss:.4f})")

    # 测试集
    model.load_state_dict(torch.load(model_path, map_location=DEVICE))
    evaluate(model, test_loader, DEVICE, phase="Test")

# ---------- 主函数 ----------
def train_all_specs():
    spec_set = set()
    for label_name in [OK_DIRNAME, NG_DIRNAME]:
        label_path = os.path.join(DATA_SAVE_DIR, label_name)
        if not os.path.isdir(label_path):
            continue
        for barcode in os.listdir(label_path):
            barcode_path = os.path.join(label_path, barcode)
            if not os.path.isdir(barcode_path):
                continue
            for spec in os.listdir(barcode_path):
                spec_path = os.path.join(barcode_path, spec)
                if os.path.isdir(spec_path):
                    spec_set.add(spec)
    if not spec_set:
        print("未找到任何规格数据，请检查 DATA_SAVE_DIR")
        return
    print(f"发现规格: {spec_set}")
    for spec in spec_set:
        train_spec(spec, DATA_SAVE_DIR, MODEL_DIR)

if __name__ == "__main__":
    train_all_specs()