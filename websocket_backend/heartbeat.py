import time
import threading
from plc_manager import plc_manager  # ← 使用共享连接
from config import HEARTBEAT_REG, HEARTBEAT_INTERVAL

class Heartbeat:
    def __init__(self):
        self.running = False
        self.thread = None
        self.counter = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _run(self):
        print("[心跳] 线程启动 (共享PLC连接)")
        while self.running:
            try:
                self.counter = (self.counter + 1) % 65536
                plc_manager.write_word(HEARTBEAT_REG, self.counter)
                time.sleep(HEARTBEAT_INTERVAL)
            except Exception as e:
                print(f"[心跳] 写入失败: {e}")
                time.sleep(1)
        print("[心跳] 线程退出")