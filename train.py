import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm
from sklearn.metrics import classification_report, confusion_matrix

from config import CONFIG
from dataset import get_dataloaders
from model import Accel1DCNN


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

    cm = confusion_matrix(all_labels, all_preds, labels=[0, 1])
    print("Confusion Matrix (rows=true, cols=pred) labels=[OK,NG]:")
    print(cm)

    rep = classification_report(all_labels, all_preds, output_dict=True, zero_division=0)
    ng_recall = rep.get("1", {}).get("recall", 0.0)
    macro_f1 = rep.get("macro avg", {}).get("f1-score", 0.0)
    acc = rep.get("accuracy", 0.0)

    return avg_loss, {"ng_recall": ng_recall, "macro_f1": macro_f1, "acc": acc}


def _plot_curves(history: dict, save_dir: str):
    """
    画两张图：
      1) loss_curve.png: train_loss & val_loss
      2) acc_curve.png : train_acc  & val_acc
    """
    import matplotlib.pyplot as plt

    os.makedirs(save_dir, exist_ok=True)
    epochs = np.arange(1, len(history["train_loss"]) + 1)

    # Loss curve (train + val)
    plt.figure(figsize=(9, 5))
    plt.plot(epochs, history["train_loss"], marker="o", linewidth=2, label="Train Loss")
    plt.plot(epochs, history["val_loss"], marker="o", linewidth=2, label="Val Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title("Loss Curve (Train vs Val)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, "loss_curve.png"), dpi=200)
    plt.close()

    # Acc curve (train + val)
    plt.figure(figsize=(9, 5))
    plt.plot(epochs, history["train_acc"], marker="o", linewidth=2, label="Train Acc")
    plt.plot(epochs, history["val_acc"], marker="o", linewidth=2, label="Val Acc")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy")
    plt.title("Accuracy Curve (Train vs Val)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, "acc_curve.png"), dpi=200)
    plt.close()


def train_main():
    train_loader, val_loader, test_loader = get_dataloaders()

    device = CONFIG["DEVICE"]
    model = Accel1DCNN(in_ch=CONFIG["CHANNELS"], num_classes=2).to(device)
    print(f"模型初始化完成，运行在: {device}")

    optimizer = optim.AdamW(model.parameters(), lr=CONFIG["LR"], weight_decay=CONFIG["WEIGHT_DECAY"])
    criterion = nn.CrossEntropyLoss()

    # 按 val_loss 最小保存
    best_val_loss = float("inf")
    os.makedirs(CONFIG["SAVE_DIR"], exist_ok=True)

    # 记录训练/验证曲线
    history = {
        "train_loss": [],
        "val_loss": [],
        "train_acc": [],
        "val_acc": [],
    }

    for epoch in range(CONFIG["EPOCHS"]):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        pbar = tqdm(train_loader, total=len(train_loader), desc=f"Epoch {epoch+1}/{CONFIG['EPOCHS']}")
        for X, y, lengths in pbar:
            X = X.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)
            logits = model(X)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            preds = torch.argmax(logits, dim=1)
            total += y.size(0)
            correct += (preds == y).sum().item()

            pbar.set_postfix(loss=f"{loss.item():.4f}", acc=f"{100.0*correct/max(total,1):.2f}%")

        train_loss = running_loss / max(len(train_loader), 1)
        train_acc = correct / max(total, 1)

        val_loss, val_metrics = evaluate(model, val_loader, device, phase="Validation")
        val_acc = val_metrics["acc"]

        # 记录
        history["train_loss"].append(train_loss)
        history["train_acc"].append(train_acc)
        history["val_loss"].append(val_loss)
        history["val_acc"].append(val_acc)

        print(
            f"[Epoch {epoch+1}] "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}"
        )

        # 保存：val_loss 最小
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), CONFIG["MODEL_SAVE_PATH"])
            print(f"🌟 保存最佳模型: val_loss={best_val_loss:.4f} -> {CONFIG['MODEL_SAVE_PATH']}")

    # 画曲线（训练集 + 验证集）
    try:
        _plot_curves(history, CONFIG["SAVE_DIR"])
        print(f"📈 曲线已保存到: {CONFIG['SAVE_DIR']}（loss_curve.png, acc_curve.png）")
    except Exception as e:
        print(f"⚠️ 绘图失败（不影响训练）：{e}")

    print("\n训练结束，加载最佳模型进行测试集评估...")
    model.load_state_dict(torch.load(CONFIG["MODEL_SAVE_PATH"], map_location=device))
    evaluate(model, test_loader, device, phase="Final Test")


if __name__ == "__main__":
    train_main()