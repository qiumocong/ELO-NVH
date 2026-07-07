"""
数据缩放设置弹窗
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QPushButton
)


class ScaleDialog(QDialog):
    def __init__(self, parent=None, current_pct=100.0):
        super().__init__(parent)
        self.setWindowTitle("数据缩放设置")
        self.setFixedSize(380, 180)
        self._setup_ui(current_pct)

    def _setup_ui(self, current_pct):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # 说明
        hint = QLabel("设置后所有 XYZ 振动数据将按比例缩放显示\n（不影响原始数据采集）")
        hint.setStyleSheet("font-size: 13px; color: #666;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 缩放比例
        row = QHBoxLayout()
        lb = QLabel("缩放比例:")
        lb.setStyleSheet("font-size: 15px;")
        row.addWidget(lb)

        self._pct_spin = QDoubleSpinBox()
        self._pct_spin.setRange(1, 1000)
        self._pct_spin.setValue(current_pct)
        self._pct_spin.setDecimals(0)
        self._pct_spin.setSuffix(" %")
        self._pct_spin.setFixedHeight(40)
        self._pct_spin.setStyleSheet("font-size: 16px;")
        row.addWidget(self._pct_spin)
        layout.addLayout(row)

        layout.addStretch()

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("确认")
        ok_btn.setFixedHeight(40)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A90D9; color: white;
                border: none; border-radius: 4px;
                padding: 6px 24px; font-size: 15px;
            }
            QPushButton:hover { background-color: #357ABD; }
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    @property
    def scale_factor(self):
        return self._pct_spin.value() / 100.0
