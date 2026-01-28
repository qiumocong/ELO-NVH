import torch
import torch.nn as nn

class FusedMotorClassifier(nn.Module):
    def __init__(self, input_channels=2, num_classes=2):
        super(FusedMotorClassifier, self).__init__()
        
        # 特征提取器
        self.features = nn.Sequential(
            # 输入: (B, 2, TOTAL_LEN)
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