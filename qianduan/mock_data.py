"""
模拟数据源模块

作用：模拟后端的行为，开发阶段不需要真实后端就能调试界面。

为什么需要这个？
- 开发前端时，后端可能还没写好
- 用模拟数据可以独立开发和测试界面
- 模拟的流程和真实后端完全一致：连接 → 选模型 → 推数据 → 出结果

和 WebSocketClient 的区别：
- WebSocketClient 真的去连接服务器
- MockDataSource 在本地自己生成假数据，流程完全模拟
- 两者的信号接口一样，MainWindow 可以无缝切换
"""

import math
import random
from PyQt5.QtCore import QObject, pyqtSignal, QTimer


class MockDataSource(QObject):
    """
    模拟数据源，模拟真实后端流程：
    连接 → 等用户选模型 → 返回工件ID → 推送数据 → 返回检测结果
    """

    # ---- 信号定义（和 WebSocketClient 完全一样）----
    data_received = pyqtSignal(dict)       # 传感器数据
    obj_id_received = pyqtSignal(str)      # 工件 ID
    model_list_received = pyqtSignal(list) # 模型列表
    result_received = pyqtSignal(dict)     # 检测结果
    connection_changed = pyqtSignal(bool)  # 连接状态

    def __init__(self, interval_ms: int = 50, batch_size: int = 10, auto_start: bool = False):
        """
        参数:
            interval_ms: 每隔多少毫秒推送一批数据（50ms = 每秒 20 批）
            batch_size: 每批包含多少个数据点（10 个点/批）
            auto_start: True=启动后立即推送数据（标注模式用），False=等选模型后才推（检测模式用）
        """
        super().__init__()
        self.interval_ms = interval_ms
        self.batch_size = batch_size
        self._auto_start = auto_start

        # QTimer：定时器，每隔 interval_ms 毫秒触发一次 _generate_batch
        self._timer = QTimer()
        self._timer.timeout.connect(self._generate_batch)

        self._time = 0.0       # 当前时间（秒），每次生成数据后递增
        self._dt = 0.001       # 时间步长：1/1000 = 0.001 秒（对应 1000Hz 采样率）
        self._running = False
        self._obj_id = "OBJ_MOCK_001"  # 模拟的工件 ID

        # 检测结果定时器（单次触发，到了时间就返回结果）
        self._result_timer = QTimer()
        self._result_timer.setSingleShot(True)  # 只触发一次
        self._result_timer.timeout.connect(self._emit_result)

    def start(self):
        """
        启动数据源。
        - auto_start=True（标注模式）：立即开始推送数据
        - auto_start=False（检测模式）：只报告连接，等用户选模型后才推数据
        """
        if self._running:
            return
        self._running = True
        self.connection_changed.emit(True)  # 通知：已连接

        if self._auto_start:
            # 标注模式：直接开始推送数据
            self._time = 0.0
            self._timer.start(self.interval_ms)
        else:
            # 检测模式：发送模型列表，等待用户选择
            self.model_list_received.emit(["模型A", "模型B", "模型C"])

    def stop(self):
        """停止所有数据推送"""
        self._running = False
        self._timer.stop()
        self._result_timer.stop()
        self.connection_changed.emit(False)

    def send_model(self, model_id: str):
        """
        用户选择了模型后调用。
        模拟后端确认模型 → 返回工件 ID → 开始推送数据。
        """
        print(f"[Mock] selected model: {model_id}")
        # 后端确认模型后，返回当前工件的编号
        self.obj_id_received.emit(self._obj_id)
        # 重置时间，开始推送数据
        self._time = 0.0
        self._timer.start(self.interval_ms)
        # 10 秒后返回检测结果（模拟一次检测的时长）
        self._result_timer.start(10000)

    def send_start(self):
        """开始检测（模拟用，实际由 send_model 触发）"""
        print("[Mock] start detection")

    def send_stop(self):
        """停止检测"""
        print("[Mock] stop detection")
        self._timer.stop()

    def send_label(self, label: int):
        """发送人工标注结果（数据集标注模式用）"""
        label_text = "OK" if label == 1 else "NG"
        print(f"[Mock] label submitted: {label_text} ({label})")

    def _generate_batch(self):
        """
        每隔 interval_ms 毫秒调用一次，生成一批模拟数据。

        生成的数据特点：
        - x: 50Hz 正弦波 + 噪声（模拟某个方向的振动）
        - y: 120Hz 正弦波 + 噪声
        - z: 80Hz 正弦波 + 噪声
        - 电流: 缓慢漂移 + 噪声（模拟电流的自然波动）
        """
        if not self._running:
            return

        times = []
        xs, ys, zs, currents = [], [], [], []

        for _ in range(self.batch_size):
            t = self._time
            times.append(round(t, 6))

            # x 方向：50Hz 振动 + 随机噪声
            xs.append(math.sin(2 * math.pi * 50 * t) * 1.0 + random.gauss(0, 0.05))
            # y 方向：120Hz 振动 + 随机噪声
            ys.append(math.sin(2 * math.pi * 120 * t) * 0.6 + random.gauss(0, 0.03))
            # z 方向：80Hz 振动 + 随机噪声
            zs.append(math.sin(2 * math.pi * 80 * t) * 0.8 + random.gauss(0, 0.04))
            # 电流：基础值 1.5A + 缓慢波动 + 噪声
            currents.append(1.5 + 0.3 * math.sin(2 * math.pi * 5 * t) + random.gauss(0, 0.02))

            self._time += self._dt  # 时间前进一个步长

        # 发射信号，把这批数据传给 MainWindow
        self.data_received.emit({
            "type": "data_batch",
            "obj_id": self._obj_id,
            "time": times,
            "x": xs,
            "y": ys,
            "z": zs,
            "current": currents,
        })

    def _emit_result(self):
        """返回模拟的检测结果"""
        if self._running:
            self.result_received.emit({
                "type": "result",
                "obj_id": self._obj_id,
                "result": "OK",           # OK=合格, NG=不合格
                "score": 0.96,            # 置信度 96%
                "message": "检测合格",
            })
