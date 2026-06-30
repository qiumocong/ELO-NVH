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
        self.is_collecting = False  # 标记是否正在采集

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def on_data_chunk(self, t_chunk, data_chunk):
        """采集回调：只有在采集状态下才推送数据到WebSocket"""
        if self.is_collecting and self.running:
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
            df = pd.DataFrame({"time": t, f"ch{i}": data[i, :]})
            df.to_csv(ch_path, index=False)
        print(f"[{self.name}] 数据已保存至 {save_dir}")

    def read_plc_data(self):
        self.current_barcode = self.plc.read_barcode(
            self.station_cfg["barcode_start"], self.station_cfg["barcode_len"]
        )
        self.current_spec = self.plc.read_product_spec()
        self.current_mode = self.plc.read_mode()
        mode_str = "auto" if self.current_mode == 1 else "manual"

        print(f"[{self.name}] 条码: {self.current_barcode}")
        print(f"[{self.name}] 规格: {self.current_spec}")
        print(f"[{self.name}] 模式: {mode_str}")

        if self.current_mode == 1 and self.current_spec:
            self.model = get_model_for_spec(self.current_spec)
            print(f"[{self.name}] 已加载模型: {self.current_spec}")
        else:
            self.model = None

        websocket_server.update_station_info(
            self.name, self.current_barcode, self.current_spec, mode_str
        )

    def wait_for_condition(self, target_cmd=None, check_signals=True, timeout=None, poll_interval=0.1):
        start = time.time()
        error_count = 0

        while self.running:
            try:
                if check_signals:
                    reset = self.plc.read_reset_signal(self.name)
                    if reset:
                        reg = "R30.1" if self.name == "left" else "R30.2"
                        print(f"[{self.name}] 重置信号触发 ({reg}=1)")
                        return "reset", None

                    ready = self.plc.read_data_ready(self.name)
                    if ready:
                        reg = "R30.3" if self.name == "left" else "R30.4"
                        print(f"[{self.name}] 数据就绪信号触发 ({reg}=1)")
                        return "data_ready", None

                if target_cmd is not None:
                    cmd = self.plc.read_plc_command(self.name)
                    if cmd == target_cmd:
                        return "cmd", cmd

                error_count = 0

            except Exception as e:
                error_count += 1
                error_msg = str(e)
                if "10053" in error_msg or "10054" in error_msg or "连接" in error_msg:
                    if error_count >= 3:
                        print(f"[{self.name}] 连续错误，等待恢复...")
                        time.sleep(3)
                        error_count = 0
                    else:
                        time.sleep(0.5)
                    continue
                else:
                    print(f"[{self.name}] 等待条件异常: {e}")

            if timeout is not None and time.time() - start > timeout:
                return "timeout", None

            time.sleep(poll_interval)

        return "stopped", None

    def reset_flow(self):
        print(f"[{self.name}] 重置流程...")
        self.is_collecting = False
        try:
            shared_daq.stop()
        except:
            pass
        self.state = PC_STATUS_IDLE

    def _do_inference(self, data):
        """
        执行推理判定
        返回: (label, score)
        label: 0=OK, 1=NG
        """
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

            result_str = "OK" if label == 0 else "NG"
            print(f"[{self.name}] 自动判定: {result_str} (置信度 {score:.3f})")
            websocket_server.send_result(self.name, result_str, score, "自动判定")

        else:  # 人工
            print(f"[{self.name}] 等待人工判定...")
            timeout = 30
            start_wait = time.time()
            result_val = None

            while time.time() - start_wait < timeout:
                # 人工判定期间检测重置信号
                try:
                    if self.plc.read_reset_signal(self.name):
                        print(f"[{self.name}] 人工判定期间重置")
                        self.reset_flow()
                        raise Exception("重置信号触发")
                except:
                    pass

                # 检查WebSocket标注
                label_val = websocket_server.get_pending_label(self.name)
                if label_val is not None:
                    result_val = 1 if label_val == 1 else 2
                    break

                # 检查PLC人工结果
                try:
                    val = self.plc.read_manual_result(self.name)
                    if val in (1, 2):
                        result_val = val
                        break
                except:
                    pass

                time.sleep(0.5)

            if result_val is None:
                result_val = 2  # 默认NG

            label = 0 if result_val == 1 else 1
            result_str = "OK" if label == 0 else "NG"
            print(f"[{self.name}] 人工判定: {result_str}")
            websocket_server.send_result(self.name, result_str, 1.0, "人工判定")

        return label, score

    def run(self):
        print(f"[{self.name}] 线程启动")
        print(f"[{self.name}] 数据就绪: R30.{3 if self.name == 'left' else 4}")
        print(f"[{self.name}] 重置信号: R30.{1 if self.name == 'left' else 2}")

        while self.running:
            try:
                # ============================================================
                # 阶段1: 等待数据就绪 或 READY命令
                # ============================================================
                print(f"[{self.name}] 等待数据就绪信号或READY命令...")
                reason, value = self.wait_for_condition(
                    target_cmd=PLC_CMD_READY,
                    check_signals=True
                )

                if reason == "stopped" or not self.running:
                    break

                if reason == "reset":
                    self.reset_flow()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待超时")
                    continue

                # 读取数据并回复就绪
                self.read_plc_data()
                self.plc.write_pc_status(self.name, PC_STATUS_READY)
                self.state = PC_STATUS_READY
                print(f"[{self.name}] PC就绪 (状态={PC_STATUS_READY})")

                # ============================================================
                # 阶段2: 等待START命令
                # ============================================================
                print(f"[{self.name}] 等待START命令...")
                reason, value = self.wait_for_condition(
                    target_cmd=PLC_CMD_START,
                    check_signals=True
                )

                if reason == "stopped" or not self.running:
                    break

                if reason == "reset":
                    self.reset_flow()
                    continue

                if reason == "data_ready":
                    self.read_plc_data()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待START超时")
                    continue

                print(f"[{self.name}] 收到START命令，开始采集...")

                # 标记采集状态
                self.is_collecting = True

                if not shared_daq.is_running:
                    shared_daq.start()
                    time.sleep(0.5)

                self.plc.write_pc_status(self.name, PC_STATUS_COLLECTING)
                self.state = PC_STATUS_COLLECTING
                print(f"[{self.name}] 采集已启动")

                # ============================================================
                # 阶段3: 等待FIRST_END命令
                # ============================================================
                print(f"[{self.name}] 等待FIRST_END命令...")
                reason, value = self.wait_for_condition(
                    target_cmd=PLC_CMD_FIRST_END,
                    check_signals=True
                )

                if reason == "stopped" or not self.running:
                    break

                if reason == "reset":
                    self.reset_flow()
                    continue

                if reason == "data_ready":
                    self.read_plc_data()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待FIRST_END超时")
                    self.reset_flow()
                    continue

                print(f"[{self.name}] 收到FIRST_END命令")
                # # 停止采集（但保持数据）
                # if shared_daq.is_running:
                #     shared_daq.stop()
                self.plc.write_pc_status(self.name, PLC_CMD_FIRST_END)

                # ============================================================
                # 阶段4: 等待SECOND_START命令
                # ============================================================
                print(f"[{self.name}] 等待SECOND_START命令...")
                reason, value = self.wait_for_condition(
                    target_cmd=PLC_CMD_SECOND_START,
                    check_signals=True
                )

                if reason == "stopped" or not self.running:
                    break

                if reason == "reset":
                    self.reset_flow()
                    continue

                if reason == "data_ready":
                    self.read_plc_data()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待SECOND_START超时")
                    self.reset_flow()
                    continue

                print(f"[{self.name}] 收到SECOND_START命令")
                # # 重新启动采集，时间连续（reset_time=False）
                # if not shared_daq.is_running:
                #     shared_daq.start(reset_time=False)
                self.plc.write_pc_status(self.name, PLC_CMD_SECOND_START)

                # ============================================================
                # 阶段5: 等待STOP命令
                # ============================================================
                print(f"[{self.name}] 等待STOP命令...")
                reason, value = self.wait_for_condition(
                    target_cmd=PLC_CMD_STOP,
                    check_signals=True
                )

                if reason == "stopped" or not self.running:
                    break

                if reason == "reset":
                    self.reset_flow()
                    continue

                if reason == "data_ready":
                    self.read_plc_data()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待STOP超时")
                    self.reset_flow()
                    continue

                print(f"[{self.name}] 收到STOP命令，停止采集...")

                # 停止采集，不再推送数据
                self.is_collecting = False
                if shared_daq.is_running:
                    shared_daq.stop()

                # ---- 获取采集数据 ----
                if self.name == "left":
                    t, data = shared_daq.get_left_data()
                else:
                    t, data = shared_daq.get_right_data()

                self.state = PC_STATUS_PROCESSING

                if t.size == 0:
                    print(f"[{self.name}] 无数据")
                    self.plc.write_result(self.name, 2)
                    self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                    self.state = PC_STATUS_IDLE
                    continue

                # ---- 执行推理 ----
                label, score = self._do_inference(data)

                # ---- 写入结果 ----
                result_code = 1 if label == 0 else 2
                self.plc.write_result(self.name, result_code)
                print(f"[{self.name}] 结果已写入: {result_code}")

                # ---- 保存数据 ----
                self.save_per_channel(t, data, label)

                # ---- 回复完成 ----
                self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                self.state = PC_STATUS_IDLE
                print(f"[{self.name}] 处理完成\n")
                # 清空WebSocket缓冲，避免旧数据残留
                websocket_server.clear_buffers()

            except Exception as e:
                if "重置" in str(e):
                    continue
                print(f"[{self.name}] 异常: {e}")
                import traceback
                traceback.print_exc()
                try:
                    self.plc.write_pc_status(self.name, PC_STATUS_ERROR)
                except:
                    pass
                self.is_collecting = False
                self.state = PC_STATUS_IDLE
                time.sleep(1)

        print(f"[{self.name}] 线程退出")