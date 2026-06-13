"""
顶部栏组件

作用：显示当前工件 ID 和模型选择下拉框。

用户操作流程：
1. 启动程序 → 显示 "工件 ID: ——"
2. 选择模型 → 从下拉框选一个
3. 点击"确认" → 触发 model_selected 信号 → 数据源收到后开始推送数据
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt5.QtCore import pyqtSignal


class HeaderWidget(QWidget):
    """顶部栏：工件 ID 显示 + 模型选择"""

    # 信号：用户点了确认按钮后发射，携带选中的模型名称
    model_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)  # 固定高度 70 像素
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)  # 水平布局
        layout.setContentsMargins(20, 10, 20, 10)  # 内边距加大

        # --- 左侧：工件 ID ---
        self._obj_label = QLabel("工件 ID: ——")
        self._obj_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        layout.addWidget(self._obj_label)

        layout.addStretch()  # 弹性空间，把后面的控件推到右边

        # --- 右侧：模型选择 ---
        model_label = QLabel("选择模型:")
        model_label.setStyleSheet("font-size: 18px; color: #555;")
        layout.addWidget(model_label)

        # 下拉框：列出可选模型
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(160)
        self._model_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                font-size: 16px;
            }
        """)
        layout.addWidget(self._model_combo)

        # 确认按钮
        self._confirm_btn = QPushButton("确认")
        self._confirm_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 24px;
                background-color: #4A90D9;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #357ABD; }
        """)
        self._confirm_btn.clicked.connect(self._on_confirm)  # 点击时调用 _on_confirm
        layout.addWidget(self._confirm_btn)

    def set_obj_id(self, obj_id: str):
        """更新工件 ID 显示（由 MainWindow 调用）"""
        self._obj_label.setText(f"工件 ID: {obj_id}")

    def set_model_list(self, models: list):
        """更新模型列表（由 MainWindow 调用）"""
        self._model_combo.clear()
        self._model_combo.addItems(models)

    def _on_confirm(self):
        """用户点了"确认"按钮"""
        model = self._model_combo.currentText()
        if model:
            self.model_selected.emit(model)  # 发射信号，通知数据源
