"""
振动图 Y 轴范围设置弹窗
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QPushButton
)
from PyQt5.QtCore import Qt


class SettingsDialog(QDialog):
    def __init__(self, parent=None, y_min=-1.0, y_max=1.0):
        super().__init__(parent)
        self.setWindowTitle("振动图设置")
        self.setFixedSize(420, 280)
        self._setup_ui(y_min, y_max)

    def _setup_ui(self, y_min, y_max):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 最小值
        row1 = QHBoxLayout()
        lb = QLabel("纵轴最小值:")
        lb.setStyleSheet("font-size: 14px;")
        row1.addWidget(lb)
        self._min_spin = QDoubleSpinBox()
        self._min_spin.setRange(-9999, 9999)
        self._min_spin.setValue(y_min)
        self._min_spin.setDecimals(2)
        self._min_spin.setFixedHeight(36)
        row1.addWidget(self._min_spin)
        layout.addLayout(row1)

        # 最大值
        row2 = QHBoxLayout()
        lb2 = QLabel("纵轴最大值:")
        lb2.setStyleSheet("font-size: 14px;")
        row2.addWidget(lb2)
        self._max_spin = QDoubleSpinBox()
        self._max_spin.setRange(-9999, 9999)
        self._max_spin.setValue(y_max)
        self._max_spin.setDecimals(2)
        self._max_spin.setFixedHeight(36)
        row2.addWidget(self._max_spin)
        layout.addLayout(row2)

        layout.addStretch()

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        auto_btn = QPushButton("自动")
        auto_btn.setFixedHeight(40)
        auto_btn.clicked.connect(self._on_auto)
        btn_row.addWidget(auto_btn)

        ok_btn = QPushButton("确认")
        ok_btn.setFixedHeight(40)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A90D9; color: white;
                border: none; border-radius: 4px;
                padding: 6px 20px; font-size: 14px;
            }
            QPushButton:hover { background-color: #357ABD; }
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

    def _on_auto(self):
        """点击'自动'：关闭弹窗，外部根据 auto_mode 恢复自动范围"""
        self._auto_mode = True
        self.accept()

    @property
    def values(self):
        return self._min_spin.value(), self._max_spin.value()

    @property
    def auto_mode(self):
        return getattr(self, '_auto_mode', False)
