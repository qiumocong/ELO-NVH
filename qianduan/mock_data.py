"""
模拟数据源模块 — 模拟后端 WebSocket 推送行为
"""

import math
import random
from PyQt5.QtCore import QObject, pyqtSignal, QTimer


class MockDataSource(QObject):
    """模拟后端流程：连接 → 发送工位信息 → 推送数据 → 返回结果"""

    data_received = pyqtSignal(dict)
    info_received = pyqtSignal(dict)
    model_list_received = pyqtSignal(list)
    result_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(self, interval_ms: int = 50, batch_size: int = 10, auto_start: bool = False):
        super().__init__()
        self.interval_ms = interval_ms
        self.batch_size = batch_size
        self._auto_start = auto_start
        self._timer = QTimer()
        self._timer.timeout.connect(self._generate_batch)
        self._time = 0.0
        self._dt = 0.001
        self._running = False
        self._obj_id = "OBJ_MOCK_001"

        # 启动后延迟推送数据的定时器（模拟 PLC 触发）
        self._start_delay_timer = QTimer()
        self._start_delay_timer.setSingleShot(True)
        self._start_delay_timer.timeout.connect(self._start_data_push)

        self._result_timer = QTimer()
        self._result_timer.setSingleShot(True)
        self._result_timer.timeout.connect(self._emit_result)

    def start(self):
        if self._running:
            return
        self._running = True
        self.connection_changed.emit(True)

        # 发送模型列表（后端始终会发）
        self.model_list_received.emit(["model_A", "model_B"])

        # 发送左工位信息
        self.info_received.emit({
            "type": "info", "side": "left",
            "barcode": self._obj_id + "_L",
            "spec": "规格A",
            "mode": "auto",
        })
        # 发送右工位信息
        self.info_received.emit({
            "type": "info", "side": "right",
            "barcode": self._obj_id + "_R",
            "spec": "规格B",
            "mode": "manual",
        })

        if self._auto_start:
            # 标注模式：立即开始推送
            self._time = 0.0
            self._timer.start(self.interval_ms)
        else:
            # 检测模式：2 秒后自动开始推送（模拟 PLC 触发）
            self._start_delay_timer.start(2000)

    def _start_data_push(self):
        self._time = 0.0
        self._timer.start(self.interval_ms)
        # 10 秒后返回检测结果
        self._result_timer.start(10000)

    def stop(self):
        self._running = False
        self._timer.stop()
        self._start_delay_timer.stop()
        self._result_timer.stop()
        self.connection_changed.emit(False)

    def send_start(self):
        print("[Mock] start detection")

    def send_stop(self):
        print("[Mock] stop detection")
        self._timer.stop()

    def send_label(self, side: str, label: int):
        label_text = "OK" if label == 1 else "NG"
        print(f"[Mock] label submitted: {side} {label_text} ({label})")

    def _generate_batch(self):
        """生成左右两组模拟数据"""
        if not self._running:
            return

        times = []
        l_xs, l_ys, l_zs, l_currents = [], [], [], []
        r_xs, r_ys, r_zs, r_currents = [], [], [], []

        for _ in range(self.batch_size):
            t = self._time
            times.append(round(t, 6))

            # 左侧：chirp 10→100Hz (x), 120Hz(y), 80Hz(z)
            f0, f1, t1 = 10, 100, 1.0
            l_phase = 2 * math.pi * (f0 * t + (f1 - f0) * t**3 / (3 * t1**2))
            l_xs.append(math.sin(l_phase) * 0.8 + random.gauss(0, 0.1))
            l_ys.append(
                math.sin(2 * math.pi * 120 * t) * 0.5
                + math.sin(2 * math.pi * 240 * t) * 0.15
                + random.gauss(0, 0.15)
            )
            l_zs.append(
                math.sin(2 * math.pi * 80 * t) * 0.6
                + math.sin(2 * math.pi * 160 * t) * 0.2
                + random.gauss(0, 0.18)
            )
            l_currents.append(1.5 + 0.3 * math.sin(2 * math.pi * 5 * t) + random.gauss(0, 0.05))

            # 右侧：chirp 30→150Hz (x), 90Hz(y), 60Hz(z)
            f0_r, f1_r = 30, 150
            r_phase = 2 * math.pi * (f0_r * t + (f1_r - f0_r) * t**3 / (3 * t1**2))
            r_xs.append(math.sin(r_phase) * 0.7 + random.gauss(0, 0.1))
            r_ys.append(
                math.sin(2 * math.pi * 90 * t) * 0.55
                + math.sin(2 * math.pi * 180 * t) * 0.2
                + random.gauss(0, 0.12)
            )
            r_zs.append(
                math.sin(2 * math.pi * 60 * t) * 0.65
                + math.sin(2 * math.pi * 120 * t) * 0.15
                + random.gauss(0, 0.16)
            )
            r_currents.append(1.8 + 0.25 * math.sin(2 * math.pi * 6 * t) + random.gauss(0, 0.04))

            self._time += self._dt

        self.data_received.emit({
            "type": "data_batch",
            "time": times,
            "left_x": l_xs, "left_y": l_ys, "left_z": l_zs, "left_current": l_currents,
            "right_x": r_xs, "right_y": r_ys, "right_z": r_zs, "right_current": r_currents,
        })

    def _emit_result(self):
        if self._running:
            self.result_received.emit({
                "type": "result", "side": "left",
                "result": "OK", "score": 0.96, "message": "左侧检测合格",
            })
            self.result_received.emit({
                "type": "result", "side": "right",
                "result": "NG", "score": 0.32, "message": "右侧检测不合格",
            })
