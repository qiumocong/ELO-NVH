"""
主窗口模块 — 双组数据版本

布局结构：
┌─────────────────────────────────────────────────────────────────┐
│  StatusBarWidget                                                  │
├──────────┬─────────────────────┬─────────────────────────────────┤
│ 左工件ID  │ 左X时域 │ 左X频谱   │ 右X时域 │ 右X频谱               │
│ 右工件ID  ├─────────────────────┼─────────────────────────────────┤
│ [模型▼]   │ 左Y时域 │ 左Y频谱   │ 右Y时域 │ 右Y频谱               │
│ [确认]    ├─────────────────────┼─────────────────────────────────┤
│          │ 左Z时域 │ 左Z频谱   │ 右Z时域 │ 右Z频谱               │
│ ┌──────┐ ├─────────────────────┼─────────────────────────────────┤
│ │左结果 │ │ 左电流              │ 右电流                           │
│ ├──────┤ │                     │                                   │
│ │右结果 │ │                     │                                   │
│ └──────┘ │                     │                                   │
└──────────┴─────────────────────┴─────────────────────────────────┘
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame
)
from PyQt5.QtCore import Qt
from config import VIBRATION_CHANNELS
from ui.status_bar import StatusBarWidget
from ui.time_chart import TimeChart
from ui.spectrum_chart import SpectrumChart
from ui.result_panel import ResultPanel

SIDES = ["left", "right"]
ALL_CHANNELS = ["x", "y", "z", "current"]


class MainWindow(QMainWindow):
    """主窗口：双组数据 + 双推理结果"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("XXX 检测系统")
        self.setMinimumSize(1400, 800)
        self.resize(1600, 900)

        # 时域图: self._charts["left"]["x"], self._charts["right"]["y"], ...
        self._charts = {side: {} for side in SIDES}
        # 频谱图: self._spectrum_charts["left"]["x"], ...
        self._spectrum_charts = {side: {} for side in SIDES}

        self._data_started = False
        self._source = None

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 状态栏 ---
        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        main_layout.addWidget(sep)

        # --- 主内容区 ---
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ========== 左侧面板 ==========
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_panel.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #e0e0e0;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 20, 12, 12)
        left_layout.setSpacing(10)

        # 左工件 ID
        self._obj_label_left = QLabel("左工件 ID: ——")
        self._obj_label_left.setFixedHeight(36)
        self._obj_label_left.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        left_layout.addWidget(self._obj_label_left)

        # 右工件 ID
        self._obj_label_right = QLabel("右工件 ID: ——")
        self._obj_label_right.setFixedHeight(36)
        self._obj_label_right.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        left_layout.addWidget(self._obj_label_right)

        # 模型选择
        model_label = QLabel("选择模型:")
        model_label.setStyleSheet("font-size: 14px; color: #555;")
        left_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setFixedHeight(36)
        self._model_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                font-size: 14px;
            }
        """)
        left_layout.addWidget(self._model_combo)

        self._confirm_btn = QPushButton("确认")
        self._confirm_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                background-color: #4A90D9;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #357ABD; }
        """)
        self._confirm_btn.clicked.connect(self._on_confirm)
        left_layout.addWidget(self._confirm_btn)

        # 分隔线
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #ddd;")
        left_layout.addWidget(sep2)

        # 左推理结果 — 上半
        self._result_panel_left = ResultPanel("左侧检测结果")
        left_layout.addWidget(self._result_panel_left, stretch=1)

        # 分隔
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("color: #ccc;")
        left_layout.addWidget(sep3)

        # 右推理结果 — 下半
        self._result_panel_right = ResultPanel("右侧检测结果")
        left_layout.addWidget(self._result_panel_right, stretch=1)

        content_layout.addWidget(left_panel)

        # ========== 右侧图表区 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        # 第1行：X — 左时域/左频谱 | 右时域/右频谱
        # 第2行：Y — 同上
        # 第3行：Z — 同上
        for ch in VIBRATION_CHANNELS:  # ["x", "y", "z"]
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            for side in SIDES:
                time_chart = TimeChart(f"{side}_{ch}")
                self._charts[side][ch] = time_chart
                row_layout.addWidget(time_chart, stretch=1)

                spectrum_chart = SpectrumChart(f"{side}_{ch}")
                self._spectrum_charts[side][ch] = spectrum_chart
                row_layout.addWidget(spectrum_chart, stretch=1)

            right_layout.addWidget(row, stretch=1)

        # 第4行：电流 — 左电流 | 右电流
        current_row = QWidget()
        current_layout = QHBoxLayout(current_row)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.setSpacing(6)
        for side in SIDES:
            chart = TimeChart(f"{side}_current")
            self._charts[side]["current"] = chart
            current_layout.addWidget(chart, stretch=1)
        right_layout.addWidget(current_row, stretch=1)

        content_layout.addWidget(right_panel, stretch=1)
        main_layout.addWidget(content, stretch=1)

    def _on_confirm(self):
        model = self._model_combo.currentText()
        if model and self._source:
            self._source.send_model(model)

    def connect_data_source(self, source):
        self._source = source
        source.data_received.connect(self._on_data)
        source.result_received.connect(self._on_result)
        source.obj_id_received.connect(self._on_obj_id)
        source.model_list_received.connect(self._on_model_list)
        source.connection_changed.connect(self._on_connection_changed)

    def _on_data(self, msg: dict):
        if not self._data_started:
            self._data_started = True
            self._status_bar.set_detect_status("检测中")

        times = msg.get("time", [])
        if not times:
            t = msg.get("timestamp", 0)
            times = [t]
            for side in SIDES:
                for ch in ALL_CHANNELS:
                    val = msg.get(f"{side}_{ch}")
                    if val is not None:
                        self._charts[side][ch].add_data([t], [val])
        else:
            for side in SIDES:
                for ch in ALL_CHANNELS:
                    values = msg.get(f"{side}_{ch}", [])
                    if values:
                        self._charts[side][ch].add_data(times, values)

        # 更新频谱图
        for side in SIDES:
            for ch in VIBRATION_CHANNELS:
                chart = self._charts[side][ch]
                if len(chart._values) >= 16:
                    self._spectrum_charts[side][ch].update_from_time_data(list(chart._values))

    def _on_result(self, msg: dict):
        result_text = msg.get("result", "")
        score = msg.get("score", 0.0)
        message = msg.get("message", "")
        # 结果可以带 side 字段区分左右
        side = msg.get("side", "left")
        if side == "right":
            self._result_panel_right.set_result(result_text, score, message)
        else:
            self._result_panel_left.set_result(result_text, score, message)
        self._status_bar.set_detect_status("完成")

    def _on_obj_id(self, obj_id: str):
        side = obj_id.get("side", "left") if isinstance(obj_id, dict) else "left"
        oid = obj_id.get("obj_id", obj_id) if isinstance(obj_id, dict) else obj_id
        if side == "right":
            self._obj_label_right.setText(f"右工件 ID: {oid}")
        else:
            self._obj_label_left.setText(f"左工件 ID: {oid}")

    def _on_model_list(self, models: list):
        self._model_combo.clear()
        self._model_combo.addItems(models)

    def _on_connection_changed(self, connected: bool):
        self._status_bar.set_connected(connected)
