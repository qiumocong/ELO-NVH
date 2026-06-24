import pymcprotocol
import time
from config import PLC_IP, PLC_PORT, STATIONS

class PLCClient:
    def __init__(self, ip=PLC_IP, port=PLC_PORT):
        self.ip = ip
        self.port = port
        self.client = None

    def connect(self):
        self.client = pymcprotocol.Type3E()
        self.client.setaccessopt(commtype="binary")
        self.client.connect(self.ip, self.port)
        print(f"[PLC] 连接 {self.ip}:{self.port} 成功")

    def close(self):
        if self.client:
            self.client.close()
            print("[PLC] 连接关闭")

    def read_word(self, reg):
        return self.client.batchread_wordunits(reg, 1)[0]

    def write_word(self, reg, val):
        self.client.batchwrite_wordunits(reg, [val])

    def read_words(self, reg, count):
        return self.client.batchread_wordunits(reg, count)

    def write_words(self, reg, vals):
        self.client.batchwrite_wordunits(reg, vals)

    def read_barcode(self, start_reg, max_len=40):
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
        words = self.read_words("R11", max_len)
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
        return self.read_word("R10")

    # ---- 工位操作 ----
    def read_station_step(self, name):
        return self.read_word(STATIONS[name]["plc_step_reg"])

    def write_pc_step(self, name, val):
        self.write_word(STATIONS[name]["pc_step_reg"], val)

    def read_manual_result(self, name):
        return self.read_word(STATIONS[name]["manual_result_reg"])

    def write_auto_result(self, name, val):
        self.write_word(STATIONS[name]["auto_result_reg"], val)