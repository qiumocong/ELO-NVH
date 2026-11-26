"""
WebSocket 客户端模块

功能：连接后端 WebSocket 服务器，接收实时数据，发送控制指令。

为什么要用独立线程？
- WebSocket 需要持续监听服务器消息（阻塞式等待）
- PyQt5 的界面更新必须在主线程
- 所以 WebSocket 跑在子线程，收到数据后通过"信号"传给主线程更新界面
- 这样界面不会卡住

信号（pyqtSignal）是什么？
- PyQt5 的信号机制，类似"事件通知"
- 子线程 emit（发射）信号 → 主线程的槽函数自动被调用
- 线程安全，不用担心多线程冲突
"""

import json
import asyncio
import threading
from PyQt5.QtCore import QObject, pyqtSignal


class WebSocketClient(QObject):
    """WebSocket 客户端，在独立线程中运行，通过 Qt 信号与主线程通信。"""

    data_received = pyqtSignal(dict)
    result_received = pyqtSignal(dict)
    info_received = pyqtSignal(dict)       # 工位信息: barcode, spec, mode
    model_list_received = pyqtSignal(list)
    connection_changed = pyqtSignal(bool)
    # 带连接序号的比例专用事件，避免重连后迟到的旧确认/发送失败更新新连接。
    scale_connection_changed = pyqtSignal(bool, int)
    scale_state_received = pyqtSignal(dict)
    scale_ack_received = pyqtSignal(dict)
    scale_send_failed = pyqtSignal(dict)
    supports_scale_protocol = True

    def __init__(self, url: str = "ws://localhost:8080", reconnect_interval: int = 3):
        super().__init__()
        self.url = url                  # WebSocket 服务器地址
        self.reconnect_interval = reconnect_interval  # 断线重连间隔（秒）
        self._ws = None                 # WebSocket 连接对象
        self._loop = None               # asyncio 事件循环（跑在子线程里）
        self._thread = None             # 子线程对象
        self._connect_task = None
        self._running = False           # 是否正在运行
        self._connected = False         # 是否已连接
        self.connection_serial = 0

    def send_scale_message(self, msg, connection_serial):
        """比例消息不跨连接排队；成功排队仍须等 scale_ack 才算确认。"""
        loop, ws = self._loop, self._ws
        if (not self._connected or connection_serial != self.connection_serial
                or loop is None or not loop.is_running() or ws is None):
            return False
        coroutine = self._send_scale(msg, ws, connection_serial)
        try:
            asyncio.run_coroutine_threadsafe(coroutine, loop)
            return True
        except RuntimeError:
            coroutine.close()
            return False

    async def _send_scale(self, msg, ws, serial):
        try:
            if self._ws is not ws or serial != self.connection_serial:
                raise RuntimeError("比例消息所属连接已结束")
            await ws.send(json.dumps(msg, allow_nan=False))
        except Exception:
            self.scale_send_failed.emit({"connection_serial": serial, "message": msg})

    def start(self):
        """启动 WebSocket 客户端线程"""
        if self._running:
            return
        self._running = True
        # 创建守护线程（daemon=True 表示主程序退出时线程自动结束）
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止客户端"""
        self._running = False
        loop = self._loop
        if loop and loop.is_running():
            # 取消连接协程，让 async with 正常关闭 socket；不能直接停仍有任务的循环。
            def cancel_connection():
                if self._connect_task is not None:
                    self._connect_task.cancel()
            try:
                loop.call_soon_threadsafe(cancel_connection)
            except RuntimeError:
                pass

    def send_message(self, msg: dict):
        """线程安全地发送消息给后端"""
        if self._loop and self._ws:
            # run_coroutine_threadsafe 让 asyncio 协程在子线程的事件循环中执行
            asyncio.run_coroutine_threadsafe(self._send(msg), self._loop)

    def send_start(self):
        """告诉后端开始检测"""
        self.send_message({"type": "start"})

    def send_stop(self):
        """告诉后端停止检测"""
        self.send_message({"type": "stop"})

    def send_label(self, side: str, label: int):
        """发送人工标注结果（数据集标注模式用）"""
        self.send_message({"type": "label", "side": side, "label": label})

    @property
    def connected(self) -> bool:
        """当前是否已连接"""
        return self._connected

    def _run_loop(self):
        """在独立线程中运行 asyncio 事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._connect_task = self._loop.create_task(self._connect_loop())
        try:
            self._loop.run_until_complete(self._connect_task)
        except asyncio.CancelledError:
            pass
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    async def _connect_loop(self):
        """持续尝试连接，断线自动重连"""
        import websockets
        while self._running:
            try:
                # 尝试连接服务器
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    self._connected = True
                    self.connection_serial += 1
                    self.scale_connection_changed.emit(True, self.connection_serial)
                    self.connection_changed.emit(True)  # 通知主线程：已连接
                    await self._receive_loop(ws)         # 开始接收消息
            except Exception as e:
                if self._running:  # 第一次重试时打印
                    print(f"[WS] 连接失败 ({type(e).__name__}: {e})，{self.reconnect_interval}s 后重试...")
            finally:
                self._ws = None
                self._connected = False
                self.scale_connection_changed.emit(False, self.connection_serial)
                self.connection_changed.emit(False)  # 通知主线程：已断开

            # 等待一段时间后重试
            if self._running:
                await asyncio.sleep(self.reconnect_interval)

    async def _receive_loop(self, ws):
        """持续接收后端消息并分发"""
        from websockets.exceptions import ConnectionClosed
        try:
            async for raw in ws:  # 每收到一条消息就执行一次循环
                try:
                    msg = json.loads(raw)  # 解析 JSON
                except json.JSONDecodeError:
                    continue  # 不是合法 JSON，跳过
                self._dispatch(msg)  # 根据消息类型分发
        except ConnectionClosed:
            pass  # 连接断开，退出循环

    async def _send(self, msg: dict):
        """发送 JSON 消息给后端"""
        if self._ws:
            try:
                await self._ws.send(json.dumps(msg))
            except Exception:
                pass

    def _dispatch(self, msg: dict):
        """
        根据消息类型分发到对应信号。

        后端发来的消息都有 "type" 字段，比如：
        - {"type": "data_batch", "time": [...], "x": [...], ...}  → 传感器数据
        - {"type": "result", "result": "OK", "score": 0.96}      → 检测结果
        - {"type": "obj_id", "obj_id": "OBJ202601010001"}        → 工件编号
        - {"type": "model_list", "models": ["模型A", "模型B"]}    → 模型列表
        """
        if not isinstance(msg, dict):
            return
        msg_type = msg.get("type", "")
        if msg_type in ("data", "data_batch"):
            self.data_received.emit(msg)
        elif msg_type == "result":
            self.result_received.emit(msg)
        elif msg_type in ("info", "obj_id"):
            self.info_received.emit(msg)
        elif msg_type == "model_list":
            self.model_list_received.emit(msg.get("models", []))
        elif msg_type in ("scale_state", "scale_ack"):
            packet = dict(msg, _connection_serial=self.connection_serial)
            signal = self.scale_state_received if msg_type == "scale_state" else self.scale_ack_received
            signal.emit(packet)
