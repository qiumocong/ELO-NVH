import time
import os
import pandas as pd
from datetime import datetime
import threading
from config import *
from plc_manager import plc_manager
from shared_data_acquisition import shared_daq  # 使用共享采集
from model_inference import get_model_for_spec, preprocess, predict
import websocket_server


class StationWorker:
    def __init__(self, name):
        self.name = name
        self.model = None
        self.station_cfg = STATIONS[name]
        self.plc = plc_manager

        # 注册数据回调到共享采集
        shared_daq.register_callback(self.name, self.on_data_chunk)

        self.running = True
        self.current_barcode = ""
        self.current_spec = ""
        self.current_mode = 0
        self.state = PC_STATUS_IDLE
        self.collected_t = None
        self.collected_data = None

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def on_data_chunk(self, t_chunk, data_chunk):
        """采集回调：将数据推送到WebSocket"""
        websocket_server.put_data(self.name, t_chunk, data_chunk)

    def save_per_channel(self, t, data, label):
        label_str = "OK" if label == 0 else "NG"
        safe_barcode = "".join(c for c in self.current_barcode if c.isalnum() or c in ('_', '-'))
        safe_spec = "".join(c for c in self.current_spec if c.isalnum() or c in ('_', '-'))
        if not safe_barcode:
            safe_barcode = f"NOBARCODE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not safe_spec:
            safe_spec = "UNKNOWN_SPEC"
        save_dir = os.path.join(DATA_SAVE_DIR, safe_spec, label_str, safe_barcode)
        os.makedirs(save_dir, exist_ok=True)

        for i in range(data.shape[0]):
            ch_path = os.path.join(save_dir, f"ch{i}.csv")
            df = pd.DataFrame({
                "time": t,
                f"ch{i}": data[i, :]
            })
            df.to_csv(ch_path, index=False)
        print(f"[{self.name}] 数据已保存至 {save_dir}")

    def wait_for_command(self, target_cmd, timeout=None, poll_interval=0.1):
        """等待PLC发送指定命令"""
        start = time.time()
        while self.running:
            try:
                cmd = self.plc.read_plc_command(self.name)
                if cmd == target_cmd:
                    return True, cmd
                if cmd != PLC_CMD_IDLE and cmd != 0:
                    pass  # 忽略非目标命令
            except Exception as e:
                print(f"[{self.name}] 等待命令异常: {e}")
            if timeout is not None and time.time() - start > timeout:
                return False, None
            time.sleep(poll_interval)
        return False, None

    def run(self):
        print(f"[{self.name}] 线程启动 (使用共享采集)")

        while self.running:
            try:
                # ============================================================
                # 等待PLC发送READY命令 (CMD=100)
                # ============================================================
                print(f"[{self.name}] 等待PLC发送READY命令...")
                success, cmd = self.wait_for_command(PLC_CMD_READY, timeout=None)

                if not success or not self.running:
                    continue

                print(f"[{self.name}] 收到READY命令")

                # ---- 读取PLC发送的数据 ----
                self.current_barcode = self.plc.read_barcode(
                    self.station_cfg["barcode_start"], self.station_cfg["barcode_len"]
                )
                self.current_spec = self.plc.read_product_spec()
                self.current_mode = self.plc.read_mode()
                mode_str = "auto" if self.current_mode == 1 else "manual"

                print(f"[{self.name}] 条码: {self.current_barcode}")
                print(f"[{self.name}] 规格: {self.current_spec}")
                print(f"[{self.name}] 模式: {mode_str}")

                # ---- 加载模型 ----
                if self.current_mode == 1:
                    self.model = get_model_for_spec(self.current_spec)
                    print(f"[{self.name}] 已加载模型: {self.current_spec}")
                else:
                    self.model = None

                # ---- 更新WebSocket ----
                websocket_server.update_station_info(
                    self.name, self.current_barcode, self.current_spec, mode_str
                )

                # ---- PC回复READY状态 ----
                self.plc.write_pc_status(self.name, PC_STATUS_READY)
                self.state = PC_STATUS_READY
                print(f"[{self.name}] PC回复就绪 (状态={PC_STATUS_READY})")

                # ============================================================
                # 等待PLC发送START命令 (CMD=200)
                # ============================================================
                print(f"[{self.name}] 等待PLC发送START命令...")
                success, cmd = self.wait_for_command(PLC_CMD_START, timeout=None)

                if not success or not self.running:
                    continue

                print(f"[{self.name}] 收到START命令")

                # ---- 检查共享采集是否已启动 ----
                if not shared_daq.is_running:
                    print(f"[{self.name}] 启动共享采集...")
                    shared_daq.start()
                    time.sleep(0.5)  # 等待采集稳定

                self.plc.write_pc_status(self.name, PC_STATUS_COLLECTING)
                self.state = PC_STATUS_COLLECTING
                print(f"[{self.name}] 采集已启动")

                # ============================================================
                # 等待PLC发送FIRST_END命令 (CMD=300)
                # ============================================================
                print(f"[{self.name}] 等待PLC发送FIRST_END命令...")
                success, cmd = self.wait_for_command(PLC_CMD_FIRST_END, timeout=None)

                if not success or not self.running:
                    continue

                print(f"[{self.name}] 收到FIRST_END命令")
                self.plc.write_pc_status(self.name, PLC_CMD_FIRST_END)

                # ============================================================
                # 等待PLC发送SECOND_START命令 (CMD=400)
                # ============================================================
                print(f"[{self.name}] 等待PLC发送SECOND_START命令...")
                success, cmd = self.wait_for_command(PLC_CMD_SECOND_START, timeout=None)

                if not success or not self.running:
                    continue

                print(f"[{self.name}] 收到SECOND_START命令")
                self.plc.write_pc_status(self.name, PLC_CMD_SECOND_START)

                # ============================================================
                # 等待PLC发送STOP命令 (CMD=900)
                # ============================================================
                print(f"[{self.name}] 等待PLC发送STOP命令...")
                success, cmd = self.wait_for_command(PLC_CMD_STOP, timeout=None)

                if not success or not self.running:
                    continue

                print(f"[{self.name}] 收到STOP命令，停止采集...")

                # ---- 获取该工位的采集数据 ----
                if self.name == "left":
                    t, data = shared_daq.get_left_data()
                else:
                    t, data = shared_daq.get_right_data()

                self.state = PC_STATUS_PROCESSING

                if t.size == 0:
                    print(f"[{self.name}] 警告: 无数据")
                    self.plc.write_result(self.name, 2)
                    self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                    self.state = PC_STATUS_IDLE
                    continue

                # ---- 执行判定 ----
                label = 0
                score = 0.0

                if self.current_mode == 1:  # 自动
                    if self.model is None:
                        print(f"[{self.name}] 错误: 模型未加载")
                        label = 1
                    else:
                        tensor = preprocess(data, self.name)
                        pred, score = predict(self.model, tensor)
                        label = pred

                    result_code = 1 if label == 0 else 2
                    result_str = "OK" if label == 0 else "NG"
                    print(f"[{self.name}] 自动判定: {result_str} (置信度 {score:.3f})")
                    websocket_server.send_result(self.name, result_str, score, "自动判定")

                else:  # 人工
                    print(f"[{self.name}] 等待人工判定...")
                    timeout = 30
                    start_wait = time.time()
                    result_val = None

                    while time.time() - start_wait < timeout:
                        label_val = websocket_server.get_pending_label(self.name)
                        if label_val is not None:
                            result_val = 1 if label_val == 1 else 2
                            break
                        val = self.plc.read_manual_result(self.name)
                        if val in (1, 2):
                            result_val = val
                            break
                        time.sleep(0.5)

                    if result_val is None:
                        result_val = 2

                    label = 0 if result_val == 1 else 1
                    result_str = "OK" if label == 0 else "NG"
                    print(f"[{self.name}] 人工判定: {result_str}")
                    websocket_server.send_result(self.name, result_str, 1.0, "人工判定")



                # ---- 写入结果到PLC ----
                result_code = 1 if label == 0 else 2
                self.plc.write_result(self.name, result_code)
                print(f"[{self.name}] 结果已写入PLC: {result_code}")

                # ---- PC回复完成 ----
                self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                self.state = PC_STATUS_IDLE
                print(f"[{self.name}] 处理完成，等待下一次检测\n")

                # ---- 保存数据 ----
                self.save_per_channel(t, data, label)

            except Exception as e:
                print(f"[{self.name}] 异常: {e}")
                import traceback
                traceback.print_exc()
                try:
                    self.plc.write_pc_status(self.name, PC_STATUS_ERROR)
                except:
                    pass
                self.state = PC_STATUS_IDLE
                time.sleep(1)

        print(f"[{self.name}] 线程退出")