import pymcprotocol
import time
from config import PLC_IP, PLC_PORT, STATIONS, PLC_PRODUCT_REG, PLC_MODE_REG

class PLCClient:
    def __init__(self, ip=PLC_IP, port=PLC_PORT):
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
        return self.client.batchread_wordunits(register, 1)[0]

    def write_word(self, register, value):
        self.client.batchwrite_wordunits(register, [value])

    def read_words(self, register, count):
        return self.client.batchread_wordunits(register, count)

    def write_words(self, register, values):
        self.client.batchwrite_wordunits(register, values)

    def read_barcode(self, start_reg, max_len=40):
        """读取条码字符串（最多 max_len 个字）"""
        words = self.read_words(start_reg, max_len)
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
        return text.strip('\x00')

    def read_product_spec(self, max_len=10):
        """读取产品规格名（R11起始）"""
        words = self.read_words(PLC_PRODUCT_REG, max_len)
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
        return text.strip('\x00')

    def read_mode(self):
        """读取判定模式 (1=自动, 2=人工)"""
        return self.read_word(PLC_MODE_REG)

    # ---- 工位相关操作 ----
    def read_station_step(self, name):
        reg = STATIONS[name]["plc_step_reg"]
        return self.read_word(reg)

    def write_pc_step(self, name, value):
        reg = STATIONS[name]["pc_step_reg"]
        self.write_word(reg, value)

    def read_manual_result(self, name):
        reg = STATIONS[name]["manual_result_reg"]
        return self.read_word(reg)

    def write_auto_result(self, name, value):
        reg = STATIONS[name]["auto_result_reg"]
        self.write_word(reg, value)