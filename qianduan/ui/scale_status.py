"""检测/标注窗口共用的小型比例提示，不在每张曲线上重复显示。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel


class ScaleStatusLabel(QLabel):
    def __init__(self, controller, side, parent=None):
        super().__init__(parent)
        self.controller, self.side = controller, side
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(True)
        self.setStyleSheet(
            "font-size: 12px; color: #243746; border: none; padding: 0px; background: transparent;"
        )
        self.setToolTip(
            "显示比例只影响曲线；本轮保存比例以后端确认为准。"
            "本轮首次成功修改后锁定，结束时冻结。"
            "比例确认不代表文件已写入；原始数据始终保持原值。"
        )
        controller.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.setText(self.controller.side_text(self.side))
