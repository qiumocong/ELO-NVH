import time
import os
import numpy as np
import pandas as pd
from datetime import datetime
import threading
from config import *
from plc_manager import plc_manager
from shared_data_acquisition import shared_daq
from model_inference import get_model_for_spec, preprocess, predict
import websocket_server
import matplotlib.pyplot as plt
from scipy.io import wavfile


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
        self.is_collecting = False

        # 记录各段样本索引
        self.start_sample = 0
        self.first_end_sample = 0
        self.second_start_sample = 0
        self.stop_sample = 0

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
        print(f"[{self.name}] 训练数据已保存至 {save_dir}")

    def _save_positive_negative_data(self, t1, data1, t2, data2, label):
        """
        保存正转（第一段）和反转（第二段）数据、图像、音频
        目录结构：NEW_DATA_SAVE_DIR/{年}/{年月日}/{OK/NG}/{条码}/{时分}/
            forward/  (正转数据、图像、音频)
            backward/ (反转数据、图像、音频)
        """
        if not ENABLE_NEW_SAVE:
            return

        try:
            # 构建时间目录
            now = datetime.now()
            year = now.strftime("%Y")
            ymd = now.strftime("%Y%m%d")
            hm = now.strftime("%H%M")
            label_str = "OK" if label == 0 else "NG"
            safe_barcode = "".join(c for c in self.current_barcode if c.isalnum() or c in ('_', '-'))
            if not safe_barcode:
                safe_barcode = f"NOBARCODE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            base_dir = os.path.join(NEW_DATA_SAVE_DIR, year, ymd, label_str, safe_barcode, hm)
            os.makedirs(base_dir, exist_ok=True)

            # 保存正转（forward）和反转（backward）数据
            segments = [
                ("forward", t1, data1),
                ("backward", t2, data2)
            ]

            for seg_name, t, data in segments:
                if t.size == 0:
                    continue
                seg_dir = os.path.join(base_dir, seg_name)
                os.makedirs(seg_dir, exist_ok=True)

                # 保存 CSV（5通道：x,y,z,voltage,current）
                csv_path = os.path.join(seg_dir, f"{seg_name}_data.csv")
                df = pd.DataFrame({
                    "time": t,
                    "x": data[0, :],
                    "y": data[1, :],
                    "z": data[2, :],
                    "voltage": data[3, :],
                    "current": data[4, :]
                })
                df.to_csv(csv_path, index=False)

                # 生成振动时域图（x,y,z）
                fig_vib, ax_vib = plt.subplots(figsize=(10, 6))
                ax_vib.plot(t, data[0, :], label="X", alpha=0.8)
                ax_vib.plot(t, data[1, :], label="Y", alpha=0.8)
                ax_vib.plot(t, data[2, :], label="Z", alpha=0.8)
                ax_vib.set_xlabel("时间 (s)")
                ax_vib.set_ylabel("加速度 (m/s²)")
                ax_vib.set_title(f"{self.name} {seg_name} 振动信号")
                ax_vib.legend()
                ax_vib.grid(True)
                vib_img_path = os.path.join(seg_dir, f"{seg_name}_vibration.png")
                plt.savefig(vib_img_path, dpi=150, bbox_inches="tight")
                plt.close(fig_vib)

                # 生成电流图（与电压一起，或单独电流）
                fig_cur, ax_cur = plt.subplots(figsize=(10, 6))
                ax_cur.plot(t, data[4, :], label="Current", color="red")
                ax_cur.set_xlabel("时间 (s)")
                ax_cur.set_ylabel("电流 (A)")
                ax_cur.set_title(f"{self.name} {seg_name} 电流信号")
                ax_cur.legend()
                ax_cur.grid(True)
                cur_img_path = os.path.join(seg_dir, f"{seg_name}_current.png")
                plt.savefig(cur_img_path, dpi=150, bbox_inches="tight")
                plt.close(fig_cur)

                # 生成音频（使用 x 轴振动信号）
                # 归一化到 [-1, 1]，再转为 int16
                audio_data = data[0, :]
                if np.max(np.abs(audio_data)) > 0:
                    audio_norm = audio_data / np.max(np.abs(audio_data))
                else:
                    audio_norm = audio_data
                audio_int16 = (audio_norm * 32767).astype(np.int16)
                audio_path = os.path.join(seg_dir, f"{seg_name}_audio.wav")
                wavfile.write(audio_path, int(self.sr), audio_int16)

            print(f"[{self.name}] 数据已保存至 {base_dir}")

        except Exception as e:
            print(f"[{self.name}] 数据保存失败: {e}")
            import traceback
            traceback.print_exc()

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
        self.state = PC_STATUS_IDLE

    def _do_inference(self, data):
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
                try:
                    if self.plc.read_reset_signal(self.name):
                        print(f"[{self.name}] 人工判定期间重置")
                        self.reset_flow()
                        raise Exception("重置信号触发")
                except:
                    pass

                label_val = websocket_server.get_pending_label(self.name)
                if label_val is not None:
                    result_val = 1 if label_val == 1 else 2
                    break

                try:
                    val = self.plc.read_manual_result(self.name)
                    if val in (1, 2):
                        result_val = val
                        break
                except:
                    pass

                time.sleep(0.5)

            if result_val is None:
                result_val = 2

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
                # 阶段1: 等待数据就绪 或 READY命令
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

                self.read_plc_data()
                self.plc.write_pc_status(self.name, PC_STATUS_READY)
                self.state = PC_STATUS_READY
                print(f"[{self.name}] PC就绪 (状态={PC_STATUS_READY})")

                # 阶段2: 等待START命令
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
                self.is_collecting = True

                # 启动共享采集（如果未运行）
                if not shared_daq.is_running:
                    shared_daq.start(reset_time=True)
                    time.sleep(0.5)

                # 记录起始样本索引
                self.start_sample = shared_daq.sample_count

                self.plc.write_pc_status(self.name, PC_STATUS_COLLECTING)
                self.state = PC_STATUS_COLLECTING
                print(f"[{self.name}] 采集已启动")

                # 阶段3: 等待FIRST_END命令
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
                self.is_collecting = False  # 停止推送
                self.first_end_sample = shared_daq.sample_count
                self.plc.write_pc_status(self.name, PLC_CMD_FIRST_END)

                # 阶段4: 等待SECOND_START命令
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
                self.is_collecting = True  # 恢复推送
                self.second_start_sample = shared_daq.sample_count
                self.plc.write_pc_status(self.name, PLC_CMD_SECOND_START)

                # 阶段5: 等待STOP命令
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
                self.is_collecting = False
                self.stop_sample = shared_daq.sample_count

                # 获取该工位的数据段（两段拼接）
                # 第一段: start_sample ~ first_end_sample
                t1, data1 = shared_daq.get_data_slice(self.name, self.start_sample, self.first_end_sample)
                # 第二段: second_start_sample ~ stop_sample
                t2, data2 = shared_daq.get_data_slice(self.name, self.second_start_sample, self.stop_sample)

                # 拼接数据
                if t1.size > 0 and t2.size > 0:
                    t = np.concatenate([t1, t2])
                    data = np.concatenate([data1, data2], axis=1)
                elif t1.size > 0:
                    t, data = t1, data1
                elif t2.size > 0:
                    t, data = t2, data2
                else:
                    t, data = np.array([]), np.empty((5, 0))

                self.state = PC_STATUS_PROCESSING

                if t.size == 0:
                    print(f"[{self.name}] 无数据")
                    self.plc.write_result(self.name, 2)
                    self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                    self.state = PC_STATUS_IDLE
                    continue

                # 推理
                label, score = self._do_inference(data)

                # 写入结果
                result_code = 1 if label == 0 else 2
                self.plc.write_result(self.name, result_code)
                print(f"[{self.name}] 结果已写入: {result_code}")

                # 保存数据
                self._save_positive_negative_data(t1, data1, t2, data2, label)
                self.save_per_channel(t, data, label)

                # 回复完成
                self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                self.state = PC_STATUS_IDLE
                print(f"[{self.name}] 处理完成\n")
                # 清空WebSocket缓冲（只清空本工位）
                websocket_server.clear_buffer(self.name)

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