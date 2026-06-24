"""
人工标注面板组件 — 支持左右双侧

作用：让人工判断当前数据是合格还是不合格。
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, pyqtSignal


class LabelerPanel(QWidget):
    """人工标注面板：合格/不合格 + 确认提交"""

    # side: "left" 或 "right", label: 1=OK, 0=NG
    label_submitted = pyqtSignal(str, int)

    def __init__(self, side: str = "left", parent=None):
        super().__init__(parent)
        self.side = side
        self.side_label = "左侧" if side == "left" else "右侧"
        self._pending_label = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 标题
        title = QLabel(f"{self.side_label}标注")
        title.setFixedHeight(32)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 提示文字
        self._hint_label = QLabel("观察图表后\n选择当前数据的标签")
        self._hint_label.setStyleSheet("font-size: 16px; color: #888;")
        self._hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint_label)

        # ========== 第一步：选择标签 ==========
        self._select_group = QWidget()
        select_layout = QVBoxLayout(self._select_group)
        select_layout.setContentsMargins(0, 0, 0, 0)
        select_layout.setSpacing(8)

        self._ok_btn = QPushButton("合  格")
        self._ok_btn.setFixedHeight(70)
        self._ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #45A049; }
            QPushButton:pressed { background-color: #388E3C; }
        """)
        self._ok_btn.clicked.connect(lambda: self._on_select(1))
        select_layout.addWidget(self._ok_btn, stretch=1)

        self._ng_btn = QPushButton("不合格")
        self._ng_btn.setFixedHeight(70)
        self._ng_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #D44332; }
            QPushButton:pressed { background-color: #C0392B; }
        """)
        self._ng_btn.clicked.connect(lambda: self._on_select(0))
        select_layout.addWidget(self._ng_btn, stretch=1)

        layout.addWidget(self._select_group, stretch=1)

        # ========== 第二步：确认/取消（初始隐藏）==========
        self._confirm_group = QWidget()
        confirm_layout = QVBoxLayout(self._confirm_group)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        confirm_layout.setSpacing(8)

        self._preview_label = QLabel("")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #F39C12;")
        confirm_layout.addWidget(self._preview_label)

        self._submit_btn = QPushButton("确认提交")
        self._submit_btn.setFixedHeight(56)
        self._submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 22px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self._submit_btn.clicked.connect(self._on_submit)
        confirm_layout.addWidget(self._submit_btn, stretch=1)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #757575; }
        """)
        self._cancel_btn.clicked.connect(self._on_cancel)
        confirm_layout.addWidget(self._cancel_btn)

        layout.addWidget(self._confirm_group, stretch=1)
        self._confirm_group.hide()

        # ========== 状态显示 ==========
        self._status_frame = QFrame()
        self._status_frame.setFrameShape(QFrame.StyledPanel)
        self._status_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        status_layout = QVBoxLayout(self._status_frame)

        self._status_label = QLabel("未标注")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #888;")
        status_layout.addWidget(self._status_label)

        self._count_label = QLabel("")
        self._count_label.setAlignment(Qt.AlignCenter)
        self._count_label.setStyleSheet("font-size: 13px; color: #999;")
        status_layout.addWidget(self._count_label)

        layout.addWidget(self._status_frame)

        self._ok_count = 0
        self._ng_count = 0
        self._update_count()

    def _on_select(self, label: int):
        self._pending_label = label
        self._select_group.hide()
        self._confirm_group.show()

        if label == 1:
            self._preview_label.setText(f"即将标注为: 合格")
            self._preview_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #4CAF50;")
            self._hint_label.setText("请再次确认图表数据")
            self._hint_label.setStyleSheet("font-size: 16px; color: #4CAF50;")
        else:
            self._preview_label.setText(f"即将标注为: 不合格")
            self._preview_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #E74C3C;")
            self._hint_label.setText("请再次确认图表数据")
            self._hint_label.setStyleSheet("font-size: 16px; color: #E74C3C;")

    def _on_submit(self):
        if self._pending_label is None:
            return

        label = self._pending_label
        self._pending_label = None

        if label == 1:
            self._ok_count += 1
            self._status_label.setText(f"已提交: 合格")
            self._status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #4CAF50;")
            self._status_frame.setStyleSheet("""
                QFrame {
                    background-color: #E8F5E9;
                    border: 2px solid #4CAF50;
                    border-radius: 8px;
                    padding: 6px;
                }
            """)
        else:
            self._ng_count += 1
            self._status_label.setText(f"已提交: 不合格")
            self._status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #E74C3C;")
            self._status_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFEBEE;
                    border: 2px solid #E74C3C;
                    border-radius: 8px;
                    padding: 6px;
                }
            """)

        self._update_count()
        self._reset_to_select()
        self.label_submitted.emit(self.side, label)

    def _on_cancel(self):
        self._pending_label = None
        self._reset_to_select()

    def _reset_to_select(self):
        self._confirm_group.hide()
        self._select_group.show()
        self._hint_label.setText("观察图表后\n选择当前数据的标签")
        self._hint_label.setStyleSheet("font-size: 16px; color: #888;")

    def _update_count(self):
        total = self._ok_count + self._ng_count
        self._count_label.setText(
            f"OK {self._ok_count} / NG {self._ng_count} / 共 {total}"
        )
