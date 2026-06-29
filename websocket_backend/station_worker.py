import time
import os
import pandas as pd
from datetime import datetime
import threading
from config import *
from plc_manager import plc_manager
from shared_data_acquisition import shared_daq
from model_inference import get_model_for_spec, preprocess, predict
import websocket_server


class StationWorker:
    def __init__(self, name):
        self.name = name
        self.model = None
        self.station_cfg = STATIONS[name]
        self.plc = plc_manager

        shared_daq.register_callback(self.name, self.on_data_chunk)

        self.running = True
        self.current_barcode = ""
        self.current_spec = ""
        self.current_mode = 0
        self.state = PC_STATUS_IDLE
        self.barcode_valid = False   # 新增：记录条码是否有效

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def on_data_chunk(self, t_chunk, data_chunk):
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

    def wait_for_command(self, target_cmd, timeout=None):
        """
        等待 PLC 发送 target_cmd。
        返回值: (success, cmd, ready_interrupt)
            success: 是否在超时前收到目标命令
            cmd: 实际读到的命令值
            ready_interrupt: 若为 True，表示在等待过程中收到了 READY 信号，应重新开始流程
        """
        start = time.time()
        while self.running:
            try:
                cmd = self.plc.read_plc_command(self.name)
                if cmd == PLC_CMD_READY and cmd != target_cmd:
                    print(f"[{self.name}] 等待中检测到 READY 信号，中断当前等待，重新开始流程。")
                    return False, cmd, True
                if cmd == target_cmd:
                    return True, cmd, False
            except Exception as e:
                print(f"[{self.name}] 等待命令异常: {e}")
            if timeout is not None and time.time() - start > timeout:
                return False, None, False
            time.sleep(POLL_INTERVAL)
        return False, None, False

    def run(self):
        print(f"[{self.name}] 线程启动 (使用共享采集)")

        while self.running:
            try:
                # ==========================================================
                # 1. 等待 READY 命令
                # ==========================================================
                print(f"[{self.name}] 等待PLC发送READY命令...")
                success, cmd, ready_interrupt = self.wait_for_command(PLC_CMD_READY, timeout=None)

                if not success or not self.running:
                    continue

                print(f"[{self.name}] 收到READY命令")

                # ---- READY 阶段：读取一次，不发送前端 ----
                raw_barcode = self.plc.read_barcode(
                    self.station_cfg["barcode_start"], self.station_cfg["barcode_len"]
                ).strip()
                # 存储（无论是否有效）
                self.current_barcode = raw_barcode
                self.current_spec = self.plc.read_product_spec()
                self.current_mode = self.plc.read_mode()

                # 判断条码是否有效（非空且为可打印 ASCII）
                self.barcode_valid = bool(raw_barcode and all(32 <= ord(c) <= 126 for c in raw_barcode))

                print(f"[{self.name}] READY阶段读取 - 条码: {self.current_barcode}, 规格: {self.current_spec}, 模式: {'自动' if self.current_mode == 1 else '人工'}")
                if not self.barcode_valid:
                    print(f"[{self.name}] 条码无效，将在START阶段重读")

                # 回复 PC 状态为 READY（必须先回复，才能接收 START）
                self.plc.write_pc_status(self.name, PC_STATUS_READY)
                self.state = PC_STATUS_READY
                print(f"[{self.name}] PC回复就绪 (状态={PC_STATUS_READY})")

                # ==========================================================
                # 2. 等待 START 命令
                # ==========================================================
                print(f"[{self.name}] 等待PLC发送START命令...")
                success, cmd, ready_interrupt = self.wait_for_command(PLC_CMD_START, timeout=None)

                if not success or not self.running:
                    if ready_interrupt:
                        print(f"[{self.name}] 因收到 READY 信号，重新开始流程。")
                        continue
                    else:
                        continue

                print(f"[{self.name}] 收到START命令")

                # ---- START 阶段：若条码无效则重读，然后更新前端 ----
                if not self.barcode_valid:
                    print(f"[{self.name}] 重新读取条码、规格、模式...")
                    raw_barcode = self.plc.read_barcode(
                        self.station_cfg["barcode_start"], self.station_cfg["barcode_len"]
                    ).strip()
                    self.current_barcode = raw_barcode
                    self.current_spec = self.plc.read_product_spec()
                    self.current_mode = self.plc.read_mode()
                    # 更新有效性（虽然之后不再重读，但记录当前状态）
                    self.barcode_valid = bool(raw_barcode and all(32 <= ord(c) <= 126 for c in raw_barcode))
                    print(f"[{self.name}] 重读后 - 条码: {self.current_barcode}, 规格: {self.current_spec}, 模式: {'自动' if self.current_mode == 1 else '人工'}")

                # 更新前端信息（此时数据是最终的）
                mode_str = "auto" if self.current_mode == 1 else "manual"
                websocket_server.update_station_info(
                    self.name, self.current_barcode, self.current_spec, mode_str
                )

                # 加载模型（自动模式）
                if self.current_mode == 1:
                    self.model = get_model_for_spec(self.current_spec)
                    print(f"[{self.name}] 已加载模型: {self.current_spec}")
                else:
                    self.model = None

                # 启动采集（如果尚未启动）
                if not shared_daq.is_running:
                    print(f"[{self.name}] 启动共享采集...")
                    shared_daq.start()
                    time.sleep(0.5)

                # 使能数据推送并清空旧数据
                websocket_server.enable_data(self.name, True)
                websocket_server.clear_data(self.name)

                self.plc.write_pc_status(self.name, PC_STATUS_COLLECTING)
                self.state = PC_STATUS_COLLECTING
                print(f"[{self.name}] 采集已启动")

                # ==========================================================
                # 3. 等待 FIRST_END
                # ==========================================================
                print(f"[{self.name}] 等待PLC发送FIRST_END命令...")
                success, cmd, ready_interrupt = self.wait_for_command(PLC_CMD_FIRST_END, timeout=None)

                if not success or not self.running:
                    if ready_interrupt:
                        print(f"[{self.name}] 因收到 READY 信号，重新开始流程。")
                        shared_daq.stop()
                        websocket_server.enable_data(self.name, False)
                        continue
                    else:
                        continue

                print(f"[{self.name}] 收到FIRST_END命令")
                self.plc.write_pc_status(self.name, PLC_CMD_FIRST_END)

                # ==========================================================
                # 4. 等待 SECOND_START
                # ==========================================================
                print(f"[{self.name}] 等待PLC发送SECOND_START命令...")
                success, cmd, ready_interrupt = self.wait_for_command(PLC_CMD_SECOND_START, timeout=None)

                if not success or not self.running:
                    if ready_interrupt:
                        print(f"[{self.name}] 因收到 READY 信号，重新开始流程。")
                        shared_daq.stop()
                        websocket_server.enable_data(self.name, False)
                        continue
                    else:
                        continue

                print(f"[{self.name}] 收到SECOND_START命令")
                self.plc.write_pc_status(self.name, PLC_CMD_SECOND_START)

                # ==========================================================
                # 5. 等待 STOP
                # ==========================================================
                print(f"[{self.name}] 等待PLC发送STOP命令...")
                success, cmd, ready_interrupt = self.wait_for_command(PLC_CMD_STOP, timeout=None)

                if not success or not self.running:
                    if ready_interrupt:
                        print(f"[{self.name}] 因收到 READY 信号，重新开始流程。")
                        shared_daq.stop()
                        websocket_server.enable_data(self.name, False)
                        continue
                    else:
                        continue

                print(f"[{self.name}] 收到STOP命令，停止采集...")

                # 获取数据
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
                    websocket_server.enable_data(self.name, False)
                    continue

                # ---- 判定 ----
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
                    start_wait = time.time()
                    result_val = None

                    while time.time() - start_wait < MANUAL_TIMEOUT:
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

                # 写入结果
                result_code = 1 if label == 0 else 2
                self.plc.write_result(self.name, result_code)
                print(f"[{self.name}] 结果已写入PLC: {result_code}")

                self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                self.state = PC_STATUS_IDLE
                print(f"[{self.name}] 处理完成，等待下一次检测\n")

                self.save_per_channel(t, data, label)

                websocket_server.enable_data(self.name, False)

            except Exception as e:
                print(f"[{self.name}] 异常: {e}")
                import traceback
                traceback.print_exc()
                try:
                    self.plc.write_pc_status(self.name, PC_STATUS_ERROR)
                except:
                    pass
                self.state = PC_STATUS_IDLE
                websocket_server.enable_data(self.name, False)
                time.sleep(1)

        print(f"[{self.name}] 线程退出")