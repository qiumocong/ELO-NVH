import time
import threading
from plc_comm import PLCClient
from config import PLC_IP, PLC_PORT, HEARTBEAT_REG, HEARTBEAT_INTERVAL

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
        plc = PLCClient(PLC_IP, PLC_PORT)
        try:
            plc.connect()
            print("[心跳] 线程启动")
            while self.running:
                try:
                    # 写入递增计数器，也可写入时间戳
                    self.counter = (self.counter + 1) % 65536
                    plc.write_word(HEARTBEAT_REG, self.counter)
                    time.sleep(HEARTBEAT_INTERVAL)
                except Exception as e:
                    print(f"[心跳] 写入失败: {e}")
                    # 尝试重连
                    try:
                        plc.close()
                    except:
                        pass
                    time.sleep(1)
                    plc.connect()
        except Exception as e:
            print(f"[心跳] 异常: {e}")
        finally:
            plc.close()
            print("[心跳] 线程退出")