import pymcprotocol
import time
from config import *

class PLCClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.client = None

    def connect(self):
        self.client = pymcprotocol.Type3E()
        self.client.setaccessopt(commtype="binary")
        self.client.connect(self.ip, self.port)
        print(f"[PLC] 连接成功 {self.ip}:{self.port}")

    def close(self):
        if self.client:
            self.client.close()
            print("[PLC] 连接关闭")

    def read_word(self, register):
        """读取单个字寄存器"""
        return self.client.batchread_wordunits(register, 1)[0]

    def write_word(self, register, value):
        """写入单个字寄存器"""
        self.client.batchwrite_wordunits(register, [value])

    def read_words(self, register, count):
        """读取多个字"""
        return self.client.batchread_wordunits(register, count)

    def write_words(self, register, values):
        """写入多个字"""
        self.client.batchwrite_wordunits(register, values)

    def read_barcode(self, start_reg, max_len=20):
        """读取条码字符串（最多 max_len 个字）"""
        words = self.read_words(start_reg, max_len)
        # 转换为字符串（小端模式）
        text = ""
        for w in words:
            low = w & 0xFF
            high = (w >> 8) & 0xFF
            if low == 0:
                break
            text += chr(low)
            if high == 0:
                break
            text += chr(high)
        return text.strip()

    def wait_for_step(self, target_step, timeout=10.0, poll_interval=0.1):
        """等待 PLC 步骤变为 target_step，超时返回 False"""
        start = time.time()
        while time.time() - start < timeout:
            if self.read_word(PLC_STEP_REG) == target_step:
                return True
            time.sleep(poll_interval)
        return False