import pymcprotocol
import time
from config import PLC_IP, PLC_PORT, STATIONS, PLC_PRODUCT_REG, PLC_MODE_REG
import re

class PLCClient:
    def __init__(self, ip=PLC_IP, port=PLC_PORT):
        self.ip = ip
        self.port = port
        self.client = None
        self.connected = False

    def connect(self):
        self.client = pymcprotocol.Type3E()
        self.client.setaccessopt(commtype="binary")
        self.client.connect(self.ip, self.port)
        self.connected = True
        print(f"[PLC] 连接成功 {self.ip}:{self.port}")

    def close(self):
        if self.client:
            try:
                self.client.close()
            except:
                pass
            self.client = None
            self.connected = False
            print("[PLC] 连接关闭")

    def read_word(self, register):
        return self.client.batchread_wordunits(register, 1)[0]

    def write_word(self, register, value):
        self.client.batchwrite_wordunits(register, [value])

    def read_words(self, register, count):
        return self.client.batchread_wordunits(register, count)

    def write_words(self, register, values):
        self.client.batchwrite_wordunits(register, values)

    def read_bit(self, register):
        """读取位寄存器 (如 R30.1)"""
        if '.' in register:
            word_reg, bit_pos = register.split('.')
            word_value = self.read_word(word_reg)
            bit_pos = int(bit_pos)
            return bool(word_value & (1 << bit_pos))
        else:
            return self.read_word(register) != 0

    def read_barcode(self, start_reg, max_len=40):
        words = self.read_words(start_reg, max_len)
        text = ""
        for w in words:
            low = w & 0xFF
            high = (w >> 8) & 0xFF
            if low == 0:
                break
            if 32 <= low <= 126:
                text += chr(low)
            if high == 0:
                break
            if 32 <= high <= 126:
                text += chr(high)
        text = re.sub(r'[^\x20-\x7E]', '', text)
        return text.strip()

    def read_product_spec(self, max_len=10):
        words = self.read_words(PLC_PRODUCT_REG, max_len)
        text = ""
        for w in words:
            low = w & 0xFF
            high = (w >> 8) & 0xFF
            if low == 0:
                break
            if 32 <= low <= 126:
                text += chr(low)
            if high == 0:
                break
            if 32 <= high <= 126:
                text += chr(high)
        text = re.sub(r'[^\x20-\x7E]', '', text)
        return text.strip()

    def read_mode(self):
        return self.read_word(PLC_MODE_REG)

    def read_plc_command(self, name):
        reg = STATIONS[name]["plc_cmd_reg"]
        return self.read_word(reg)

    def read_data_ready(self, name):
        reg = STATIONS[name]["data_ready_reg"]
        return self.read_bit(reg)

    def read_reset_signal(self, name):
        reg = STATIONS[name]["reset_reg"]
        return self.read_bit(reg)

    def write_pc_status(self, name, status):
        reg = STATIONS[name]["pc_status_reg"]
        self.write_word(reg, status)

    def write_result(self, name, result_code):
        reg = STATIONS[name]["pc_result_reg"]
        self.write_word(reg, result_code)
        ready_reg = STATIONS[name]["pc_result_ready"]
        self.write_word(ready_reg, 1)

    def read_manual_result(self, name):
        reg = STATIONS[name]["manual_result_reg"]
        return self.read_word(reg)