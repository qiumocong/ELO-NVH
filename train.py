import torch
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm
from sklearn.metrics import classification_report

# 导入本地模块
from config import CONFIG
from model import FusedMotorClassifier
from dataset import get_dataloaders

def evaluate(model, loader, device, phase="Validation"):
    """
    通用验证/测试函数
    """
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
    
    # 打印报告
    print(f"\n--- {phase} Report ---")
    print(f"Loss: {avg_loss:.4f}")
    # digits=4 确保能看到高精度的不平衡数据指标
    print(classification_report(all_labels, all_preds, target_names=['OK', 'NG'], digits=4))
    
    # 获取 NG Recall 用于保存模型
    report_dict = classification_report(all_labels, all_preds, output_dict=True)
    # 假设 NG 的 label id 是 1，根据 labels.csv 的实际情况调整
    ng_recall = report_dict['1']['recall']
    
    return avg_loss, ng_recall

def train_main():
    # 1. 获取数据
    train_loader, val_loader, test_loader = get_dataloaders()
    
    # 2. 初始化模型
    device = CONFIG["DEVICE"]
    model = FusedMotorClassifier().to(device)
    print(f"模型初始化完成，运行在: {device}")
    
    # 3. 定义 Loss 和 Optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=CONFIG["LR"])
    
    best_ng_recall = 0.0
    
    # 4. 训练循环
    for epoch in range(CONFIG["EPOCHS"]):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        
        print(f"\nEpoch {epoch+1}/{CONFIG['EPOCHS']}")
        pbar = tqdm(train_loader, total=len(train_loader), desc="Training")
        
        for inputs, labels in pbar:
            inputs, labels = inputs.to(device), labels.to(device)
            
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
            
        # 5. 验证
        val_loss, val_ng_recall = evaluate(model, val_loader, device, phase="Validation")
        
        # 6. 保存最佳模型 (以 NG Recall 为准)
        if val_ng_recall > best_ng_recall:
            best_ng_recall = val_ng_recall
            torch.save(model.state_dict(), CONFIG["MODEL_SAVE_PATH"])
            print(f"🌟 新的最佳模型已保存! NG Recall: {best_ng_recall:.4f}")
            
    # 7. 最终测试
    print("\n训练结束，正在进行最终测试集评估...")
    model.load_state_dict(torch.load(CONFIG["MODEL_SAVE_PATH"]))
    evaluate(model, test_loader, device, phase="Final Test")

if __name__ == "__main__":
    train_main()