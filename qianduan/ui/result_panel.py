"""
检测结果面板组件

作用：显示最终的检测结果（合格/不合格/异常）。

显示状态：
- 灰色 "待检测"   → 初始状态，还没开始检测
- 绿色 "合格"     → 检测通过，产品没问题
- 红色 "不合格"   → 检测不通过，产品有问题
- 橙色 "异常"     → 其他情况（比如传感器故障）

还会显示：
- 置信度（score）：模型对结果的确定程度，比如 96%
- 消息（message）：附加说明，比如 "检测合格"
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt5.QtCore import Qt


class ResultPanel(QWidget):
    """检测结果面板（左侧栏下方）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 标题
        title = QLabel("检测结果")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        title.setAlignment(Qt.AlignCenter)  # 居中对齐
        layout.addWidget(title)

        # --- 结果状态卡片 ---
        # QFrame 是一个带边框的容器，用来做卡片效果
        self._result_frame = QFrame()
        self._result_frame.setFrameShape(QFrame.StyledPanel)
        self._result_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        frame_layout = QVBoxLayout(self._result_frame)

        # 状态文字（大字）
        self._status_label = QLabel("待检测")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #888;")
        frame_layout.addWidget(self._status_label)

        # 置信度
        self._score_label = QLabel("")
        self._score_label.setAlignment(Qt.AlignCenter)
        self._score_label.setStyleSheet("font-size: 13px; color: #666;")
        frame_layout.addWidget(self._score_label)

        # 附加消息
        self._message_label = QLabel("")
        self._message_label.setAlignment(Qt.AlignCenter)
        self._message_label.setStyleSheet("font-size: 12px; color: #888;")
        self._message_label.setWordWrap(True)  # 自动换行
        frame_layout.addWidget(self._message_label)

        layout.addWidget(self._result_frame)
        layout.addStretch()  # 底部弹性空间，让卡片靠上

    def set_result(self, result: str, score: float = 0.0, message: str = ""):
        """
        设置检测结果（由 MainWindow 调用）。

        参数:
            result: 结果字符串，"OK"/"PASS"/"合格" 都算通过
            score: 置信度，0~1 之间的小数
            message: 附加说明文字
        """
        if result.upper() in ("OK", "PASS", "合格"):
            # --- 合格：绿色 ---
            self._status_label.setText("合格")
            self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #4CAF50;")
            self._result_frame.setStyleSheet("""
                QFrame {
                    background-color: #E8F5E9;
                    border: 2px solid #4CAF50;
                    border-radius: 8px;
                    padding: 12px;
                }
            """)
        elif result.upper() in ("NG", "FAIL", "不合格"):
            # --- 不合格：红色 ---
            self._status_label.setText("不合格")
            self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #E74C3C;")
            self._result_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFEBEE;
                    border: 2px solid #E74C3C;
                    border-radius: 8px;
                    padding: 12px;
                }
            """)
        else:
            # --- 异常：橙色 ---
            self._status_label.setText(result)
            self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #F39C12;")
            self._result_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFF8E1;
                    border: 2px solid #F39C12;
                    border-radius: 8px;
                    padding: 12px;
                }
            """)

        # 显示置信度（百分比格式）
        if score > 0:
            self._score_label.setText(f"置信度: {score:.1%}")  # .1% 会把 0.96 显示为 96.0%
        else:
            self._score_label.setText("")

        self._message_label.setText(message)

    def clear(self):
        """重置为初始状态"""
        self._status_label.setText("待检测")
        self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #888;")
        self._score_label.setText("")
        self._message_label.setText("")
        self._result_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 12px;
            }
        """)
