import os
import pandas as pd
import torch
import torch.nn as nn
from model import Accel1DCNN
from config import CONFIG
from sklearn.metrics import classification_report


def preprocess_data(csv_path):
    """
    读取并预处理 CSV 文件数据
    """
    df = pd.read_csv(csv_path)
    # 假设 CSV 文件包含 'time', 'ax', 'ay', 'az' 列
    features = df[['ax', 'ay', 'az']].values
    # 转换为 PyTorch 张量
    data = torch.tensor(features, dtype=torch.float32)
    return data


def test_model(csv_path, model_path):
    """
    使用训练好的模型对 CSV 文件进行测试
    """
    device = CONFIG["DEVICE"]
    model = Accel1DCNN(in_ch=CONFIG["CHANNELS"], num_classes=2).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    # 预处理数据
    data = preprocess_data(csv_path)
    data = data.permute(1, 0).unsqueeze(0).to(device)  # Permute to [batch_size, channels, sequence_length]

    with torch.no_grad():
        logits = model(data)
        preds = torch.argmax(logits, dim=1)
        print(f"预测结果: {preds.cpu().numpy().tolist()}")
        return preds.cpu().numpy().tolist()[0]


if __name__ == "__main__":
    # 替换为你的 CSV 文件路径和模型路径
    csv_file_list = []
    pred_results = []
    true_labels = []  # 存储真实标签
    pred_labels = []  # 存储预测标签

    for root, _, files in os.walk(r"D:\qmc\PycharmProjects\yanpu\data\02-转换csv\test_data\NG"):
        for file in files:
            if file.endswith(".csv"):
                csv_file = os.path.join(root, file)
                csv_file_list.append(csv_file)
                true_labels.append(1)  # 假设文件夹 NG 对应标签 1

    model_file = CONFIG["MODEL_SAVE_PATH"]

    for csv_file in csv_file_list:
        print(f"正在测试: {csv_file}")
        test_result = test_model(csv_file, model_file)
        pred_results.append((csv_file, test_result))
        pred_labels.append(test_result)

    # Print classification report
    print("\nClassification Report:")
    print(classification_report(true_labels, pred_labels, target_names=["OK", "NG"], labels=[0, 1], digits=4))
