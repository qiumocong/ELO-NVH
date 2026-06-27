"""
状态栏组件

作用：显示 WebSocket 连接状态和检测状态。

显示内容：
- 左侧：绿色圆点 + "已连接" / 灰色圆点 + "未连接"
- 右侧：检测状态文字（待检测 / 检测中 / 完成）
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt


class StatusBarWidget(QWidget):
    """连接状态 + 检测状态显示"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)

        # --- 左侧：连接状态 ---
        # 圆点：用特殊字符 "●" 模拟指示灯，通过改变颜色表示状态
        self._conn_dot = QLabel("●")
        self._conn_dot.setStyleSheet("font-size: 20px; color: #ccc;")  # 默认灰色
        layout.addWidget(self._conn_dot)

        self._conn_label = QLabel("未连接")
        self._conn_label.setStyleSheet("font-size: 18px; color: #888;")
        layout.addWidget(self._conn_label)

        layout.addStretch()  # 弹性空间

        # --- 右侧：检测状态 ---
        self._detect_label = QLabel("检测状态: 待检测")
        self._detect_label.setStyleSheet("font-size: 18px; color: #555;")
        layout.addWidget(self._detect_label)

    def set_connected(self, connected: bool):
        """更新连接状态（只管连接指示灯，不改检测状态）"""
        if connected:
            self._conn_dot.setStyleSheet("font-size: 20px; color: #4CAF50;")  # 绿色
            self._conn_label.setText("已连接")
            self._conn_label.setStyleSheet("font-size: 18px; color: #4CAF50;")
        else:
            self._conn_dot.setStyleSheet("font-size: 20px; color: #ccc;")  # 灰色
            self._conn_label.setText("未连接")
            self._conn_label.setStyleSheet("font-size: 18px; color: #888;")
            self._detect_label.setText("检测状态: 待检测")

    def set_detect_status(self, status: str):
        """更新检测状态文字"""
        self._detect_label.setText(f"检测状态: {status}")
