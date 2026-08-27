import os
import random
import re
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from tqdm import tqdm
from model_new import Accel1DCNN
from config import DATA_SAVE_DIR, MODEL_DIR, DEVICE, MODEL_IN_CH, MODEL_NUM_CLASSES, TRAIN_CONFIG, OK_DIRNAME, NG_DIRNAME


DEFAULT_THRESHOLD = 0.5


def seed_everything(seed):
    """固定数据划分、模型初始化和 DataLoader shuffle 的随机性。"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    # 确定性算法便于复现实验；可能会略微降低 CUDA 训练速度。
    if torch.backends.cudnn.is_available():
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def seed_worker(worker_id):
    """让多进程 DataLoader 的 NumPy/Python 随机状态可复现。"""
    del worker_id
    worker_seed = torch.initial_seed() % (2 ** 32)
    np.random.seed(worker_seed)
    random.seed(worker_seed)

# ---------- 数据集 ----------
class VibrationDataset(Dataset):
    def __init__(self, data_dir, spec_name, input_indices=[0,1], max_len=None):
        self.samples = []
        self.input_indices = input_indices
        self.max_len = max_len
        spec_path = os.path.join(data_dir, spec_name)
        if not os.path.isdir(spec_path):
            return
        for label_name in [OK_DIRNAME, NG_DIRNAME]:
            label = 0 if label_name == OK_DIRNAME else 1
            label_path = os.path.join(spec_path, label_name)
            if not os.path.isdir(label_path):
                continue
            for barcode in os.listdir(label_path):
                barcode_path = os.path.join(label_path, barcode)
                if not os.path.isdir(barcode_path):
                    continue
                ch_files = [f for f in os.listdir(barcode_path) if f.startswith("ch") and f.endswith(".csv")]
                if not ch_files:
                    continue
                ch_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
                data_dict = {}
                max_len_sample = 0
                for ch_file in ch_files:
                    ch_idx = int(re.search(r'\d+', ch_file).group())
                    df = pd.read_csv(os.path.join(barcode_path, ch_file))
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

def calculate_metrics(labels, ng_probs, threshold=DEFAULT_THRESHOLD):
    """根据 NG 概率计算固定阈值下的分类指标和阈值无关指标。"""
    labels = np.asarray(labels, dtype=np.int64)
    ng_probs = np.asarray(ng_probs, dtype=np.float64)
    preds = (ng_probs >= threshold).astype(np.int64)

    report = classification_report(
        labels,
        preds,
        labels=[0, 1],
        target_names=["OK", "NG"],
        output_dict=True,
        zero_division=0,
    )
    cm = confusion_matrix(labels, preds, labels=[0, 1])

    # 分层划分正常情况下同时包含两个类别；这里保留保护逻辑，避免小数据集直接报错。
    has_both_classes = np.unique(labels).size == 2
    pr_auc = average_precision_score(labels, ng_probs) if has_both_classes else float("nan")
    roc_auc = roc_auc_score(labels, ng_probs) if has_both_classes else float("nan")
    balanced_acc = balanced_accuracy_score(labels, preds) if has_both_classes else float("nan")

    return preds, cm, {
        "threshold": float(threshold),
        "acc": float(report.get("accuracy", 0.0)),
        "ok_precision": float(report.get("OK", {}).get("precision", 0.0)),
        "ok_recall": float(report.get("OK", {}).get("recall", 0.0)),
        "ok_f1": float(report.get("OK", {}).get("f1-score", 0.0)),
        "ng_precision": float(report.get("NG", {}).get("precision", 0.0)),
        "ng_recall": float(report.get("NG", {}).get("recall", 0.0)),
        "ng_f1": float(report.get("NG", {}).get("f1-score", 0.0)),
        "macro_f1": float(report.get("macro avg", {}).get("f1-score", 0.0)),
        "balanced_acc": float(balanced_acc),
        "pr_auc": float(pr_auc),
        "roc_auc": float(roc_auc),
    }


def find_best_threshold(labels, ng_probs):
    """在验证集上选择 macro F1 最大的阈值，并以 balanced accuracy 作为次级条件。"""
    labels = np.asarray(labels, dtype=np.int64)
    ng_probs = np.asarray(ng_probs, dtype=np.float64)
    candidates = np.unique(np.concatenate(([0.0, DEFAULT_THRESHOLD, 1.0], ng_probs)))

    best_threshold = DEFAULT_THRESHOLD
    best_key = (-float("inf"), -float("inf"), -float("inf"))
    for threshold in candidates:
        preds = (ng_probs >= threshold).astype(np.int64)
        macro_f1 = f1_score(labels, preds, labels=[0, 1], average="macro", zero_division=0)
        balanced_acc = balanced_accuracy_score(labels, preds)
        # 最后优先选择更接近 0.5 的阈值，避免小验证集给出过于极端的边界。
        key = (macro_f1, balanced_acc, -abs(float(threshold) - DEFAULT_THRESHOLD))
        if key > best_key:
            best_key = key
            best_threshold = float(threshold)

    return best_threshold


def evaluate(model, loader, device, phase="Validation", threshold=DEFAULT_THRESHOLD):
    model.eval()
    criterion = nn.CrossEntropyLoss()
    all_labels, all_ng_probs = [], []
    running_loss = 0.0
    total_samples = 0

    with torch.no_grad():
        for X, y, lengths in loader:
            X = X.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            logits = model(X)
            loss = criterion(logits, y)

            # 按样本数累计，避免最后一个较小 batch 在平均 loss 中权重过高。
            batch_size = y.size(0)
            running_loss += loss.item() * batch_size
            total_samples += batch_size
            probs = torch.softmax(logits, dim=1)[:, 1]
            all_ng_probs.extend(probs.cpu().numpy().tolist())
            all_labels.extend(y.cpu().numpy().tolist())

    avg_loss = running_loss / max(total_samples, 1)
    preds, cm, metrics = calculate_metrics(all_labels, all_ng_probs, threshold)
    metrics["loss"] = float(avg_loss)

    print(f"\n--- {phase} Report ---")
    print(f"Loss: {avg_loss:.4f} | threshold: {threshold:.4f}")
    print(classification_report(
        all_labels,
        preds,
        labels=[0, 1],
        target_names=["OK", "NG"],
        digits=4,
        zero_division=0,
    ))
    print(f"Balanced Acc: {metrics['balanced_acc']:.4f} | PR-AUC: {metrics['pr_auc']:.4f} | ROC-AUC: {metrics['roc_auc']:.4f}")
    print("Confusion Matrix:")
    print(cm)
    return avg_loss, metrics, np.asarray(all_labels), np.asarray(all_ng_probs)


def save_checkpoint(path, model, epoch, spec_name, seed, val_metrics, threshold, split_indices):
    """保存可追溯的实验 checkpoint；正式部署前再导出纯 state_dict。"""
    checkpoint = {
        "model_state": model.state_dict(),
        "epoch": int(epoch),
        "spec_name": spec_name,
        "seed": int(seed),
        "threshold": float(threshold),
        "val_metrics": dict(val_metrics),
        "label_mapping": {"OK": 0, "NG": 1},
        "train_config": dict(TRAIN_CONFIG),
        "split_indices": split_indices,
    }
    torch.save(checkpoint, path)

# ---------- 训练单个规格 ----------
def train_spec(spec_name, data_dir, model_dir):
    print(f"\n===== 训练规格: {spec_name} =====")
    seed = TRAIN_CONFIG["seed"]
    seed_everything(seed)

    dataset = VibrationDataset(data_dir, spec_name, input_indices=[0, 1, 2], max_len=TRAIN_CONFIG["max_len"])
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

    # 训练集 shuffle 使用独立 generator，保证相同 seed 下 batch 顺序一致。
    train_generator = torch.Generator()
    train_generator.manual_seed(seed)

    train_loader = DataLoader(train_dataset, batch_size=TRAIN_CONFIG["batch_size"],
                              shuffle=True, collate_fn=collate_fn,
                              num_workers=TRAIN_CONFIG["num_workers"],
                              pin_memory=TRAIN_CONFIG["pin_memory"],
                              worker_init_fn=seed_worker,
                              generator=train_generator)
    val_loader = DataLoader(val_dataset, batch_size=TRAIN_CONFIG["batch_size"],
                            shuffle=False, collate_fn=collate_fn,
                            num_workers=TRAIN_CONFIG["num_workers"],
                            pin_memory=TRAIN_CONFIG["pin_memory"],
                            worker_init_fn=seed_worker)
    test_loader = DataLoader(test_dataset, batch_size=TRAIN_CONFIG["batch_size"],
                             shuffle=False, collate_fn=collate_fn,
                             num_workers=TRAIN_CONFIG["num_workers"],
                             pin_memory=TRAIN_CONFIG["pin_memory"],
                             worker_init_fn=seed_worker)

    print(f"总样本: {len(dataset)}, 训练: {len(train_dataset)}, 验证: {len(val_dataset)}, 测试: {len(test_dataset)}")
    print(
        "类别分布: "
        f"train OK/NG={sum(labels[i] == 0 for i in train_idx)}/{sum(labels[i] == 1 for i in train_idx)}, "
        f"val OK/NG={sum(labels[i] == 0 for i in val_idx)}/{sum(labels[i] == 1 for i in val_idx)}, "
        f"test OK/NG={sum(labels[i] == 0 for i in test_idx)}/{sum(labels[i] == 1 for i in test_idx)}"
    )

    model = Accel1DCNN(in_ch=MODEL_IN_CH, num_classes=MODEL_NUM_CLASSES).to(DEVICE)
    optimizer = optim.AdamW(model.parameters(), lr=TRAIN_CONFIG["lr"], weight_decay=TRAIN_CONFIG["weight_decay"])
    criterion = nn.CrossEntropyLoss()

    # 实验模型写入独立目录，避免覆盖线上按规格加载的正式模型。
    experiment_dir = os.path.join(model_dir, "experiments", spec_name)
    os.makedirs(experiment_dir, exist_ok=True)
    best_ap_path = os.path.join(experiment_dir, f"{spec_name}_best_ap.pth")
    best_val_loss_path = os.path.join(experiment_dir, f"{spec_name}_best_val_loss.pth")
    selected_model_path = os.path.join(experiment_dir, f"{spec_name}_selected.pth")

    split_indices = {
        "train": [int(i) for i in train_idx],
        "val": [int(i) for i in val_idx],
        "test": [int(i) for i in test_idx],
    }
    best_ap_key = (-float("inf"), -float("inf"), -float("inf"), -float("inf"))
    best_val_loss = float("inf")

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
            # 按样本数累计，兼容最后一个不满 batch 的情况。
            running_loss += loss.item() * y.size(0)
            preds = torch.argmax(logits, dim=1)
            total_samples += y.size(0)
            correct += (preds == y).sum().item()
            pbar.set_postfix(loss=f"{loss.item():.4f}", acc=f"{100.0*correct/max(total_samples,1):.2f}%")
        train_loss = running_loss / max(total_samples, 1)
        train_acc = correct / max(total_samples, 1)
        val_loss, val_metrics, _, _ = evaluate(
            model,
            val_loader,
            DEVICE,
            phase="Validation",
            threshold=DEFAULT_THRESHOLD,
        )
        val_acc = val_metrics["acc"]
        print(
            f"[Epoch {epoch+1}] train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f} "
            f"macro_f1={val_metrics['macro_f1']:.4f} pr_auc={val_metrics['pr_auc']:.4f}"
        )

        # 主 checkpoint 按 PR-AUC 选择，依次用 macro F1、balanced accuracy 和 val loss 打破平局。
        pr_auc = val_metrics["pr_auc"] if np.isfinite(val_metrics["pr_auc"]) else -float("inf")
        ap_key = (
            pr_auc,
            val_metrics["macro_f1"],
            val_metrics["balanced_acc"],
            -val_loss,
        )
        if ap_key > best_ap_key:
            best_ap_key = ap_key
            save_checkpoint(
                best_ap_path,
                model,
                epoch + 1,
                spec_name,
                seed,
                val_metrics,
                DEFAULT_THRESHOLD,
                split_indices,
            )
            print(
                f"保存 PR-AUC 最优模型: {best_ap_path} "
                f"(PR-AUC={val_metrics['pr_auc']:.4f}, macro_f1={val_metrics['macro_f1']:.4f})"
            )

        # 同时保留旧标准的 checkpoint，方便后续进行公平对照。
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            save_checkpoint(
                best_val_loss_path,
                model,
                epoch + 1,
                spec_name,
                seed,
                val_metrics,
                DEFAULT_THRESHOLD,
                split_indices,
            )
            print(f"保存 val_loss 最优对照模型: {best_val_loss_path} (val_loss={best_val_loss:.4f})")

    # 加载排序能力最好的模型，再单独用验证集确定最终分类阈值。
    best_checkpoint = torch.load(best_ap_path, map_location=DEVICE, weights_only=False)
    model.load_state_dict(best_checkpoint["model_state"])
    _, _, val_labels, val_ng_probs = evaluate(
        model,
        val_loader,
        DEVICE,
        phase="Validation Before Threshold Search",
        threshold=DEFAULT_THRESHOLD,
    )
    selected_threshold = find_best_threshold(val_labels, val_ng_probs)
    _, selected_val_metrics, _, _ = evaluate(
        model,
        val_loader,
        DEVICE,
        phase="Validation With Selected Threshold",
        threshold=selected_threshold,
    )

    best_checkpoint["threshold"] = selected_threshold
    best_checkpoint["val_metrics_at_selected_threshold"] = selected_val_metrics
    torch.save(best_checkpoint, selected_model_path)
    print(f"最终实验模型已保存: {selected_model_path} (threshold={selected_threshold:.4f})")

    # 测试集仅评估最终选定模型，测试结果不参与 checkpoint 或阈值选择。
    print("进行测试集评估")
    evaluate(
        model,
        test_loader,
        DEVICE,
        phase="Test",
        threshold=selected_threshold,
    )

# ---------- 主函数 ----------
def train_all_specs():
    spec_set = set()
    for spec in os.listdir(DATA_SAVE_DIR):
        spec_path = os.path.join(DATA_SAVE_DIR, spec)
        if not os.path.isdir(spec_path):
            continue
        for label_name in [OK_DIRNAME, NG_DIRNAME]:
            label_path = os.path.join(spec_path, label_name)
            if not os.path.isdir(label_path):
                continue
            if os.listdir(label_path):   # 该标签下有数据才算
                spec_set.add(spec)
    if not spec_set:
        print("未找到任何规格数据，请检查 DATA_SAVE_DIR")
        return
    print(f"发现规格: {spec_set}")
    for spec in spec_set:
        train_spec(spec, DATA_SAVE_DIR, MODEL_DIR)

if __name__ == "__main__":
    train_all_specs()
