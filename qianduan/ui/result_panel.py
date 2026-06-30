"""
检测结果面板组件 — 支持标题传入
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt5.QtCore import Qt


class ResultPanel(QWidget):
    """检测结果面板"""

    def __init__(self, title: str = "检测结果", parent=None):
        super().__init__(parent)
        self._title_text = title
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 标题
        title = QLabel(self._title_text)
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 结果状态卡片
        self._result_frame = QFrame()
        self._result_frame.setFrameShape(QFrame.StyledPanel)
        self._result_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        frame_layout = QVBoxLayout(self._result_frame)
        frame_layout.setSpacing(4)

        self._status_label = QLabel("待检测")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #888;")
        frame_layout.addWidget(self._status_label)

        self._score_label = QLabel("")
        self._score_label.setAlignment(Qt.AlignCenter)
        self._score_label.setStyleSheet("font-size: 20px; color: #666;")
        frame_layout.addWidget(self._score_label)

        self._message_label = QLabel("")
        self._message_label.setAlignment(Qt.AlignCenter)
        self._message_label.setStyleSheet("font-size: 18px; color: #888;")
        self._message_label.setWordWrap(True)
        frame_layout.addWidget(self._message_label)

        layout.addWidget(self._result_frame, stretch=1)

    def set_result(self, result: str, score: float = 0.0, message: str = ""):
        if result.upper() in ("OK", "PASS", "合格"):
            self._status_label.setText("合格")
            self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #4CAF50;")
            self._result_frame.setStyleSheet("""
                QFrame {
                    background-color: #E8F5E9;
                    border: 2px solid #4CAF50;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)
        elif result.upper() in ("NG", "FAIL", "不合格"):
            self._status_label.setText("不合格")
            self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #E74C3C;")
            self._result_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFEBEE;
                    border: 2px solid #E74C3C;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)
        else:
            self._status_label.setText(result)
            self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #F39C12;")
            self._result_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFF8E1;
                    border: 2px solid #F39C12;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)

        if score > 0:
            self._score_label.setText(f"置信度: {score:.1%}")
        else:
            self._score_label.setText("")

        self._message_label.setText(message)

    def clear(self):
        self._status_label.setText("待检测")
        self._status_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #888;")
        self._score_label.setText("")
        self._message_label.setText("")
        self._result_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 8px;
            }
        """)
