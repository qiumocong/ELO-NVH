"""
人工标注面板组件

作用：让人工判断当前数据是合格还是不合格，替代自动检测结果。

标注流程（带确认步骤）：
1. 用户观察图表
2. 点击"合格"或"不合格" → 进入预览状态（可以反悔）
3. 点击"确认提交" → 标签真正发送给后端
4. 或者点击"取消" → 回到初始状态，重新选择

为什么要加确认步骤？
- 一开始觉得合格，仔细看频谱后可能觉得不合格
- 确认前可以反复切换，确认后才算真正打标
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, pyqtSignal


class LabelerPanel(QWidget):
    """人工标注面板：合格/不合格 + 确认提交"""

    # 信号：用户确认后发射，label=1 表示合格，label=0 表示不合格
    label_submitted = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending_label = None  # 待确认的标签（还没真正提交）
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 标题
        title = QLabel("人工标注")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 提示文字
        self._hint_label = QLabel("观察图表后\n选择当前数据的标签")
        self._hint_label.setStyleSheet("font-size: 12px; color: #888;")
        self._hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint_label)

        # ========== 第一步：选择标签按钮 ==========

        self._select_group = QWidget()
        select_layout = QVBoxLayout(self._select_group)
        select_layout.setContentsMargins(0, 0, 0, 0)
        select_layout.setSpacing(8)

        # 合格按钮
        self._ok_btn = QPushButton("合格")
        self._ok_btn.setFixedHeight(50)
        self._ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #45A049; }
        """)
        self._ok_btn.clicked.connect(lambda: self._on_select(1))
        select_layout.addWidget(self._ok_btn)

        # 不合格按钮
        self._ng_btn = QPushButton("不合格")
        self._ng_btn.setFixedHeight(50)
        self._ng_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #D44332; }
        """)
        self._ng_btn.clicked.connect(lambda: self._on_select(0))
        select_layout.addWidget(self._ng_btn)

        layout.addWidget(self._select_group)

        # ========== 第二步：确认/取消按钮（初始隐藏） ==========

        self._confirm_group = QWidget()
        confirm_layout = QVBoxLayout(self._confirm_group)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        confirm_layout.setSpacing(6)

        # 预览状态文字
        self._preview_label = QLabel("")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #F39C12;")
        confirm_layout.addWidget(self._preview_label)

        # 确认提交按钮
        self._submit_btn = QPushButton("确认提交")
        self._submit_btn.setFixedHeight(44)
        self._submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self._submit_btn.clicked.connect(self._on_submit)
        confirm_layout.addWidget(self._submit_btn)

        # 取消按钮
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #757575; }
        """)
        self._cancel_btn.clicked.connect(self._on_cancel)
        confirm_layout.addWidget(self._cancel_btn)

        layout.addWidget(self._confirm_group)
        self._confirm_group.hide()  # 初始隐藏

        # ========== 状态显示区域 ==========

        self._status_frame = QFrame()
        self._status_frame.setFrameShape(QFrame.StyledPanel)
        self._status_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        status_layout = QVBoxLayout(self._status_frame)

        self._status_label = QLabel("未标注")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #888;")
        status_layout.addWidget(self._status_label)

        self._count_label = QLabel("")
        self._count_label.setAlignment(Qt.AlignCenter)
        self._count_label.setStyleSheet("font-size: 11px; color: #999;")
        status_layout.addWidget(self._count_label)

        layout.addWidget(self._status_frame)

        layout.addStretch()

        # 计数器
        self._ok_count = 0
        self._ng_count = 0
        self._update_count()

    def _on_select(self, label: int):
        """第一步：用户点了合格或不合格，进入预览状态"""
        self._pending_label = label

        # 切换到确认界面
        self._select_group.hide()
        self._confirm_group.show()

        if label == 1:
            self._preview_label.setText("即将标注为: 合格")
            self._preview_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #4CAF50;")
            self._hint_label.setText("请再次确认图表数据")
            self._hint_label.setStyleSheet("font-size: 12px; color: #4CAF50;")
        else:
            self._preview_label.setText("即将标注为: 不合格")
            self._preview_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E74C3C;")
            self._hint_label.setText("请再次确认图表数据")
            self._hint_label.setStyleSheet("font-size: 12px; color: #E74C3C;")

    def _on_submit(self):
        """第二步：用户点了确认提交，标签正式生效"""
        if self._pending_label is None:
            return

        label = self._pending_label
        self._pending_label = None

        # 更新计数
        if label == 1:
            self._ok_count += 1
            self._status_label.setText("已提交: 合格")
            self._status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #4CAF50;")
            self._status_frame.setStyleSheet("""
                QFrame {
                    background-color: #E8F5E9;
                    border: 2px solid #4CAF50;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)
        else:
            self._ng_count += 1
            self._status_label.setText("已提交: 不合格")
            self._status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E74C3C;")
            self._status_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFEBEE;
                    border: 2px solid #E74C3C;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)

        self._update_count()
        self._reset_to_select()

        # 发射信号，通知数据源把标签发给后端
        self.label_submitted.emit(label)

    def _on_cancel(self):
        """取消：回到选择状态"""
        self._pending_label = None
        self._reset_to_select()

    def _reset_to_select(self):
        """恢复到初始选择状态"""
        self._confirm_group.hide()
        self._select_group.show()
        self._hint_label.setText("观察图表后\n选择当前数据的标签")
        self._hint_label.setStyleSheet("font-size: 12px; color: #888;")

    def _update_count(self):
        total = self._ok_count + self._ng_count
        self._count_label.setText(
            f"本次会话: 合格 {self._ok_count} / 不合格 {self._ng_count} / 共 {total}"
        )

    def clear(self):
        """重置为初始状态"""
        self._pending_label = None
        self._confirm_group.hide()
        self._select_group.show()
        self._status_label.setText("未标注")
        self._status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #888;")
        self._hint_label.setText("观察图表后\n选择当前数据的标签")
        self._hint_label.setStyleSheet("font-size: 12px; color: #888;")
        self._status_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 8px;
            }
        """)
