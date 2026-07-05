import time
import threading
from plc_comm import PLCClient
from config import PLC_IP, PLC_PORT, PLC_MODE_REG


class PLCManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.plc = None
        self.connected = False
        self.running = True
        self._lock = threading.RLock()
        self._reconnect_lock = threading.Lock()
        self._is_reconnecting = False
        self._connect()
        self._heartbeat_thread = threading.Thread(target=self._keepalive, daemon=True)
        self._heartbeat_thread.start()

    def _connect(self):
        with self._lock:
            if self.connected:
                return True
            try:
                if self.plc:
                    try:
                        self.plc.close()
                    except:
                        pass
                self.plc = PLCClient(PLC_IP, PLC_PORT)
                self.plc.connect()
                self.connected = True
                print("[PLC管理器] 连接成功")
                return True
            except Exception as e:
                print(f"[PLC管理器] 连接失败: {e}")
                self.connected = False
                return False

    def _keepalive(self):
        """后台心跳，只在空闲时执行"""
        idle_count = 0
        while self.running:
            try:
                # 尝试获取锁，如果被占用则跳过本次心跳
                if self._lock.acquire(blocking=False):
                    try:
                        if self.connected and self.plc:
                            _ = self.plc.read_word(PLC_MODE_REG)
                            idle_count = 0
                    finally:
                        self._lock.release()
                else:
                    idle_count += 1
                    if idle_count > 10:
                        # 长时间无法获取锁，可能死锁，尝试重连
                        print("[PLC管理器] 心跳警告: 长时间无法获取锁")
                        idle_count = 0
                time.sleep(3)
            except Exception as e:
                if self.running:
                    print(f"[PLC管理器] 心跳异常: {e}")
                    self.connected = False
                    time.sleep(1)
                    self._connect()

    def ensure_connection(self, retry=True):
        with self._lock:
            if self.connected and self.plc:
                try:
                    _ = self.plc.read_word(PLC_MODE_REG)
                    return True
                except Exception as e:
                    error_msg = str(e)
                    if "10053" in error_msg or "10054" in error_msg or \
                            "connection" in error_msg.lower() or "timed out" in error_msg.lower():
                        self.connected = False
                    else:
                        return True

            if retry and not self._is_reconnecting:
                with self._reconnect_lock:
                    self._is_reconnecting = True
                    try:
                        if self.plc:
                            try:
                                self.plc.close()
                            except:
                                pass
                            self.plc = None
                        time.sleep(0.5)
                        return self._connect()
                    finally:
                        self._is_reconnecting = False
            return self.connected

    def _execute_with_retry(self, func, *args, **kwargs):
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                with self._lock:
                    if not self.ensure_connection(retry=(attempt > 0)):
                        raise Exception("PLC连接不可用")
                    return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_msg = str(e)
                if "10053" in error_msg or "10054" in error_msg or \
                        "connection" in error_msg.lower() or "timed out" in error_msg.lower():
                    self.connected = False
                    if attempt < max_retries - 1:
                        wait_time = 0.5 * (attempt + 1)
                        time.sleep(wait_time)
                        self._connect()
                    else:
                        raise
                else:
                    raise

        if last_error:
            raise last_error

    # ---- 基础操作 ----
    def read_word(self, register):
        return self._execute_with_retry(self.plc.read_word, register)

    def write_word(self, register, value):
        self._execute_with_retry(self.plc.write_word, register, value)

    def read_words(self, register, count):
        return self._execute_with_retry(self.plc.read_words, register, count)

    def write_words(self, register, values):
        self._execute_with_retry(self.plc.write_words, register, values)

    def read_bit(self, register):
        return self._execute_with_retry(self.plc.read_bit, register)

    def read_barcode(self, start_reg, max_len=40):
        return self._execute_with_retry(self.plc.read_barcode, start_reg, max_len)

    def read_product_spec(self, max_len=10):
        return self._execute_with_retry(self.plc.read_product_spec, max_len)

    def read_mode(self):
        return self._execute_with_retry(self.plc.read_mode)

    def read_plc_command(self, name):
        from config import STATIONS
        reg = STATIONS[name]["plc_cmd_reg"]
        return self._execute_with_retry(self.plc.read_word, reg)

    def read_data_ready(self, name):
        from config import STATIONS
        reg = STATIONS[name]["data_ready_reg"]
        return self._execute_with_retry(self.plc.read_bit, reg)

    def read_reset_signal(self, name):
        from config import STATIONS
        reg = STATIONS[name]["reset_reg"]
        return self._execute_with_retry(self.plc.read_bit, reg)

    def write_pc_status(self, name, status):
        from config import STATIONS
        reg = STATIONS[name]["pc_status_reg"]
        self._execute_with_retry(self.plc.write_word, reg, status)

    def write_result(self, name, result_code):
        from config import STATIONS
        reg = STATIONS[name]["pc_result_reg"]
        self._execute_with_retry(self.plc.write_word, reg, result_code)
        ready_reg = STATIONS[name]["pc_result_ready"]
        self._execute_with_retry(self.plc.write_word, ready_reg, 1)

    def read_manual_result(self, name):
        from config import STATIONS
        reg = STATIONS[name]["manual_result_reg"]
        return self._execute_with_retry(self.plc.read_word, reg)

    def close(self):
        self.running = False
        with self._lock:
            if self.connected and self.plc:
                try:
                    self.plc.close()
                except:
                    pass
                self.connected = False
                self.plc = None
                print("[PLC管理器] 连接已关闭")


plc_manager = PLCManager()