import time
import os
import pandas as pd
from datetime import datetime
import threading
from config import *
from plc_comm import PLCClient
from data_acquisition import DataAcquisition
from model_inference import get_model_for_spec, preprocess, predict  # 改用动态加载

class StationWorker:
    def __init__(self, name):
        self.name = name
        self.model = None                     # 将在读取规格后加载
        self.station_cfg = STATIONS[name]
        self.plc = PLCClient(PLC_IP, PLC_PORT)
        self.plc.connect()
        self.daq = DataAcquisition(
            accel_channels=self.station_cfg["accel_channels"],
            voltage_channels=self.station_cfg["voltage_channels"],
            sample_rate=SAMPLE_RATE,
            chunk_samples=CHUNK_SAMPLES,
            max_collect_time=MAX_COLLECT_TIME,
            accel_range=RANGE_9234,
            sensitivity=SENSITIVITY,
            voltage_range=RANGE_9239
        )
        self.state = "idle"
        self.running = True
        self.current_barcode = ""
        self.current_spec = ""
        self.last_heartbeat = time.time()   # 心跳计时
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.daq.stop()
        self.plc.close()

    def save_per_channel(self, t, data, label):
        """
        目录结构：DATA_SAVE_DIR/{barcode}/{label}/{spec}/
        每个通道保存为单独CSV，包含 time 和 ch_i 两列
        """
        label_str = "OK" if label == 0 else "NG"
        safe_barcode = "".join(c for c in self.current_barcode if c.isalnum() or c in ('_', '-'))
        safe_spec = "".join(c for c in self.current_spec if c.isalnum() or c in ('_', '-'))
        if not safe_barcode:
            safe_barcode = f"NOBARCODE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not safe_spec:
            safe_spec = "UNKNOWN_SPEC"
        save_dir = os.path.join(DATA_SAVE_DIR, safe_barcode, label_str, safe_spec)
        os.makedirs(save_dir, exist_ok=True)

        for i in range(data.shape[0]):
            ch_path = os.path.join(save_dir, f"ch{i}.csv")
            df = pd.DataFrame({
                "time": t,
                f"ch{i}": data[i, :]
            })
            df.to_csv(ch_path, index=False)

        print(f"[{self.name}] 数据已保存至 {save_dir}")

    def run(self):
        print(f"[{self.name}] 线程启动")
        while self.running:
            try:
                # ---------- 心跳 ----------
                now = time.time()
                if now - self.last_heartbeat >= 1.0:
                    _ = self.plc.read_mode()
                    self.last_heartbeat = now

                # ---------- 状态机 ----------
                plc_step = self.plc.read_station_step(self.name)

                if plc_step == STEP_READY and self.state == "idle":
                    self.current_barcode = self.plc.read_barcode(
                        self.station_cfg["barcode_start"], self.station_cfg["barcode_len"]
                    )
                    self.current_spec = self.plc.read_product_spec()
                    print(f"[{self.name}] 条码:{self.current_barcode} 规格:{self.current_spec}")

                    # ---- 根据规格动态加载模型 ----
                    mode_now = self.plc.read_mode()
                    if mode_now == 1:   # 自动模式
                        self.model = get_model_for_spec(self.current_spec)
                        print(f"[{self.name}] 已加载规格 {self.current_spec} 的模型")
                    else:
                        self.model = None
                        print(f"[{self.name}] 人工模式，不加载模型")

                    self.plc.write_pc_step(self.name, STEP_READY)

                elif plc_step == STEP_TEST_START and self.state == "idle":
                    print(f"[{self.name}] 开始采集")
                    self.daq.start()
                    self.state = "collecting"
                    self.plc.write_pc_step(self.name, STEP_TEST_START)

                elif plc_step == STEP_TEST_FIRST_END and self.state == "collecting":
                    self.plc.write_pc_step(self.name, STEP_TEST_FIRST_END)
                    print(f"[{self.name}] 第一段结束")

                elif plc_step == STEP_TEST_SECOND_START and self.state == "collecting":
                    self.plc.write_pc_step(self.name, STEP_TEST_SECOND_START)
                    print(f"[{self.name}] 第二段开始")

                elif plc_step == STEP_TEST_END and self.state == "collecting":
                    print(f"[{self.name}] 结束采集，处理...")
                    t, data = self.daq.stop()
                    self.state = "processing"

                    if t.size == 0:
                        print(f"[{self.name}] 无数据")
                        self.plc.write_pc_step(self.name, STEP_TEST_END)
                        self.state = "idle"
                        continue

                    if not self.current_barcode:
                        self.current_barcode = self.plc.read_barcode(
                            self.station_cfg["barcode_start"], self.station_cfg["barcode_len"]
                        )
                    if not self.current_spec:
                        self.current_spec = self.plc.read_product_spec()

                    mode_now = self.plc.read_mode()

                    if mode_now == 1:   # 自动
                        if self.model is None:
                            print(f"[{self.name}] 错误：自动模式但模型未加载")
                            label = 1   # 默认NG
                            score = 0.0
                        else:
                            tensor = preprocess(data, self.name)
                            pred, score = predict(self.model, tensor)  # 返回 (label, score)
                            label = pred
                        result_code = 1 if label == 0 else 2
                        self.plc.write_auto_result(self.name, result_code)
                        print(f"[{self.name}] 自动判定: {'OK' if label == 0 else 'NG'} (置信度 {score:.3f})")
                    else:               # 人工
                        print(f"[{self.name}] 等待人工判定...")
                        timeout = 30
                        start_wait = time.time()
                        result = None
                        while time.time() - start_wait < timeout:
                            val = self.plc.read_manual_result(self.name)
                            if val in (1, 2):
                                result = val
                                break
                            time.sleep(0.5)
                        if result is None:
                            result = 2   # 默认NG
                        label = 0 if result == 1 else 1
                        print(f"[{self.name}] 人工判定: {'OK' if label == 0 else 'NG'}")
                        self.plc.write_pc_step(self.name, STEP_TEST_END)

                    self.save_per_channel(t, data, label)
                    self.state = "idle"
                    print(f"[{self.name}] 处理完成")

                time.sleep(0.05)

            except Exception as e:
                print(f"[{self.name}] 异常: {e}")
                time.sleep(1)

        print(f"[{self.name}] 线程退出")