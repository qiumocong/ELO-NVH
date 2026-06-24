import torch
import torch.nn as nn


class Accel1DCNN(nn.Module):
    """
    可变长度输入: (B, C, T)
    输出: (B, 2)
    """
    def __init__(self, in_ch=3, num_classes=2):
        super().__init__()

        self.stem = nn.Sequential(
            nn.Conv1d(in_ch, 32, kernel_size=15, stride=2, padding=7),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2),
        )

        # dilated conv blocks
        def block(cin, cout, k, d):
            pad = (k // 2) * d
            return nn.Sequential(
                nn.Conv1d(cin, cout, kernel_size=k, stride=1, padding=pad, dilation=d),
                nn.BatchNorm1d(cout),
                nn.ReLU()
            )

        self.features = nn.Sequential(
            block(32, 64, 9, d=1),
            block(64, 64, 9, d=2),
            block(64, 128, 7, d=4),
            block(128, 128, 7, d=8),
        )

        self.pool = nn.AdaptiveAvgPool1d(1)

        self.head = nn.Sequential(
            nn.Flatten(),          # (B,128)
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        x = self.stem(x)
        x = self.features(x)
        x = self.pool(x)
        x = self.head(x)
        return x