import time
import os
import numpy as np
import pandas as pd
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import threading
from config import *
from plc_manager import plc_manager
from shared_data_acquisition import shared_daq
from model_inference import get_model_for_spec, preprocess, predict
import websocket_server
import matplotlib.pyplot as plt
from scipy.io import wavfile
if __package__:
    from .scaled_data_writer import ScaledCopyResult, write_scaled_copy
else:
    from scaled_data_writer import ScaledCopyResult, write_scaled_copy

# 设置 matplotlib 中文字体
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False


@dataclass(frozen=True)
class ChannelSaveLocation:
    """本轮只生成一次安全名称；原始、副本及分段保存复用，空条码也不会分叉。"""

    root: Path
    directory: Path
    spec_name: str
    label_name: str
    barcode_name: str


@dataclass(frozen=True)
class RoundSaveResult:
    original_saved: bool
    original_dir: Path
    scaled: Optional[ScaledCopyResult]
    original_error: Optional[str] = None


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

        # 与临时推送标志 is_collecting 分离：正反转间隔仍属于同一采集轮次。
        self._scale_lock = threading.Lock()
        self._scale_round = None
        self.frozen_scale_snapshot = None  # T6 保存时使用本轮冻结值，不读当前显示设置。

        # 记录各段样本索引（使用工位独立的样本计数）
        self.start_sample = 0
        self.first_end_sample = 0
        self.second_start_sample = 0
        self.stop_sample = 0

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._abort_scale_round("worker_stopped")
        if self.thread:
            self.thread.join(timeout=2.0)

    def _begin_scale_round(self):
        with self._scale_lock:
            if not self.running:
                return False
            self._scale_round = websocket_server.scale_sessions.begin_round(
                self.name, self.current_barcode, self.current_spec,
            )
            self.frozen_scale_snapshot = None
            current = self._scale_round
        print(f"[{self.name}] 比例轮次开始: {current.round_id}, 初始比例={current.save_scale:g}")
        websocket_server.notify_scale_state("round_started")
        return True

    def _freeze_scale_round(self):
        # 仅做内存状态切换。900 握手前不等网络、不广播、不缩放或写文件。
        with self._scale_lock:
            if self._scale_round is None:
                raise RuntimeError("比例轮次尚未开始")
            frozen = websocket_server.scale_sessions.finish_round(
                self.name, self._scale_round.round_id,
            )
            self._scale_round = frozen
            self.frozen_scale_snapshot = frozen
            return frozen

    def _abort_scale_round(self, reason):
        with self._scale_lock:
            if self._scale_round is None or self._scale_round.phase != "collecting":
                return  # 已结束的冻结快照不能被人工等待中的重置/退出改写。
            self._scale_round = websocket_server.scale_sessions.abort_round(
                self.name, self._scale_round.round_id, reason,
            )
            self.is_collecting = False  # 这一轮已经放弃，不再把旧轮数据继续推送到前端。
            current = self._scale_round
        print(f"[{self.name}] 比例轮次取消: {current.round_id}, 原因={reason}")
        websocket_server.notify_scale_state("round_aborted")

    def on_data_chunk(self, t_chunk, data_chunk):
        """采集回调：只有在采集状态下才推送数据到WebSocket"""
        if self.is_collecting and self.running:
            websocket_server.put_data(self.name, t_chunk, data_chunk)

    def _channel_save_location(self, barcode, spec, label):
        label_str = "OK" if label == 0 else "NG"
        safe_barcode = "".join(c for c in barcode if c.isalnum() or c in ('_', '-'))
        safe_spec = "".join(c for c in spec if c.isalnum() or c in ('_', '-'))
        if not safe_barcode:
            safe_barcode = f"NOBARCODE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not safe_spec:
            safe_spec = "UNKNOWN_SPEC"
        root = Path(DATA_SAVE_DIR).expanduser().absolute()
        return ChannelSaveLocation(root, root / safe_spec / label_str / safe_barcode,
                                   safe_spec, label_str, safe_barcode)

    def save_per_channel(self, t, data, label, *, save_location=None):
        """原始五通道全写成功才返回本轮位置，失败直接交给外层记录。"""
        location = save_location or self._channel_save_location(
            self.current_barcode, self.current_spec, label,
        )
        if t.ndim != 1 or not t.size or data.shape != (5, t.size):
            raise ValueError("原始训练数据必须为非空 times(N,) 和 data(5,N)")
        location.directory.mkdir(parents=True, exist_ok=True)

        for i in range(data.shape[0]):
            ch_path = location.directory / f"ch{i}.csv"
            df = pd.DataFrame({"time": t, f"ch{i}": data[i, :]})
            df.to_csv(ch_path, index=False)
        print(f"[{self.name}] 训练数据已保存至 {location.directory}")
        return location

    def _save_round_data(self, t, data, t1, data1, t2, data2, label, frozen):
        """原始 → 可选副本 → 原分段格式；各保存失败独立，不改变 PLC 判定。

        frozen 为本轮 900 时的局部不可变对象，不能在人工等待后读取全局比例或
        self.current_barcode/spec。副本绝不替代原始数据；原始失败则禁止生成副本。
        """
        if frozen.phase != "finished" or frozen.side != self.name:
            raise ValueError("保存必须使用本工位已经结束的冻结轮次")
        location = self._channel_save_location(frozen.barcode, frozen.spec, label)
        context = f"[{self.name}] round={frozen.round_id} scale={frozen.save_scale:g}"
        original_saved, original_error, scaled = False, None, None
        try:
            saved = self.save_per_channel(t, data, label, save_location=location)
            if saved != location:
                raise RuntimeError("原始保存未返回本轮成功位置，不能确认原始五通道已保存")
            original_saved = True
            print(f"{context} 原始保存成功: {location.directory}")
        except Exception as exc:
            original_error = f"{type(exc).__name__}: {exc}"
            print(f"{context} 原始保存失败: {location.directory}; {original_error}; 副本不生成")

        if original_saved:
            try:
                # 由真实原始根目录派生，副本不放进原始训练扫描树，不受新格式开关控制。
                if not location.root.name:
                    raise ValueError("原始训练根目录是磁盘根目录，无法派生同级副本目录")
                scaled_root = location.root.with_name(location.root.name + "_scaled")
                scaled = write_scaled_copy(
                    scaled_root, location.spec_name, location.label_name, location.barcode_name,
                    t, data, frozen.save_scale,
                    metadata={
                        "original_dir": str(location.directory), "side": frozen.side,
                        "round_id": frozen.round_id, "barcode": frozen.barcode, "spec": frozen.spec,
                        "label": location.label_name, "initial_scale": frozen.initial_scale,
                        "locked": frozen.locked, "session_id": frozen.session_id,
                        "change_request_id": frozen.change_request_id,
                    },
                )
            except Exception as exc:
                # T2 正常返回 failed；此处兜底派生路径/意外异常，分段保存仍继续。
                scaled = ScaledCopyResult("failed", scale=frozen.save_scale,
                                          error=f"{type(exc).__name__}: {exc}")
            print(f"{context} 副本状态={scaled.status}; 目录={scaled.directory}; 错误={scaled.error}")

        try:
            self._save_positive_negative_data(t1, data1, t2, data2, label,
                                              barcode_name=location.barcode_name)
        except Exception as exc:
            print(f"{context} 分段保存异常: {type(exc).__name__}: {exc}")
        return RoundSaveResult(original_saved, location.directory, scaled, original_error)

    def _save_positive_negative_data(self, t1, data1, t2, data2, label, *, barcode_name=None):
        """保存正转/反转数据、各轴振动图、电流图、音频（三轴）"""
        if not ENABLE_NEW_SAVE:
            return

        try:
            now = datetime.now()
            year = now.strftime("%Y")
            ymd = now.strftime("%Y%m%d")
            hm = now.strftime("%H%M")
            label_str = "OK" if label == 0 else "NG"
            safe_barcode = barcode_name
            if safe_barcode is None:
                safe_barcode = "".join(c for c in self.current_barcode if c.isalnum() or c in ('_', '-'))
            if not safe_barcode:
                safe_barcode = f"NOBARCODE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            base_dir = os.path.join(NEW_DATA_SAVE_DIR, year, ymd, label_str, safe_barcode, hm)
            os.makedirs(base_dir, exist_ok=True)

            segments = [("forward", t1, data1), ("backward", t2, data2)]

            for seg_name, t, data in segments:
                if t.size == 0:
                    continue
                seg_dir = os.path.join(base_dir, seg_name)
                os.makedirs(seg_dir, exist_ok=True)

                # 1. CSV
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

                # 2. 三轴振动图（分开保存）
                axes_plot = [(0, "X", "red"), (1, "Y", "green"), (2, "Z", "blue")]
                for ax_idx, ax_label, color in axes_plot:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ax.plot(t, data[ax_idx, :], label=f"{ax_label} 轴", color=color)
                    ax.set_xlabel("时间 (s)")
                    ax.set_ylabel("加速度 (m/s^2)")
                    ax.set_title(f"{self.name} {seg_name} 振动信号 - {ax_label}轴")
                    ax.legend()
                    ax.grid(True)
                    img_path = os.path.join(seg_dir, f"{seg_name}_vibration_{ax_label}.png")
                    plt.savefig(img_path, dpi=150, bbox_inches="tight")
                    plt.close(fig)

                # 3. 电流图
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

                # 4. 音频（三个轴分别生成）
                axes_audio = [(0, "X"), (1, "Y"), (2, "Z")]
                for ax_idx, ax_label in axes_audio:
                    audio_data = data[ax_idx, :]
                    if np.max(np.abs(audio_data)) > 0:
                        audio_norm = audio_data / np.max(np.abs(audio_data))
                    else:
                        audio_norm = audio_data
                    audio_int16 = (audio_norm * 32767).astype(np.int16)
                    audio_path = os.path.join(seg_dir, f"{seg_name}_audio_{ax_label}.wav")
                    wavfile.write(audio_path, int(SAMPLE_RATE), audio_int16)

            print(f"[{self.name}] 新格式数据已保存至 {base_dir}")

        except Exception as e:
            print(f"[{self.name}] 新数据保存失败: {e}")
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
        self._abort_scale_round("flow_reset")
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
            timeout = 300
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
                if not self._begin_scale_round():
                    break
                self.is_collecting = True

                # 启动该工位的采集（独立延迟）
                # reset_time=True, enable_delay=True 表示重置该工位数据并启用延迟
                shared_daq.start_side(self.name, reset_time=True, enable_delay=True)

                # 记录起始样本索引（延迟结束后样本计数从0开始）
                self.start_sample = 0
                # 设置 first_end_sample 为 0，稍后更新
                self.first_end_sample = 0
                self.second_start_sample = 0
                self.stop_sample = 0

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
                    self._abort_scale_round("new_data_ready")
                    self.read_plc_data()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待FIRST_END超时")
                    self.reset_flow()
                    continue

                print(f"[{self.name}] 收到FIRST_END命令")
                self.is_collecting = False  # 停止推送（但采集继续）
                # 记录第一段结束的样本索引（使用该工位的样本计数）
                self.first_end_sample = shared_daq.get_sample_count(self.name)
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
                    self._abort_scale_round("new_data_ready")
                    self.read_plc_data()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待SECOND_START超时")
                    self.reset_flow()
                    continue

                print(f"[{self.name}] 收到SECOND_START命令")
                self.is_collecting = True  # 恢复推送
                # 恢复采集（不重置，不延迟），时间连续
                shared_daq.start_side(self.name, reset_time=False, enable_delay=False)
                # 记录第二段起始样本索引
                self.second_start_sample = shared_daq.get_sample_count(self.name)
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
                    self._abort_scale_round("new_data_ready")
                    self.read_plc_data()
                    continue

                if reason == "timeout":
                    print(f"[{self.name}] 等待STOP超时")
                    self.reset_flow()
                    continue

                print(f"[{self.name}] 收到STOP命令，停止采集...")
                self.is_collecting = False
                frozen_scale = self._freeze_scale_round()
                # PLC 要求 5s 内回 900 握手确认
                self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                self.stop_sample = shared_daq.get_sample_count(self.name)
                print(f"[{self.name}] 比例轮次冻结: {frozen_scale.round_id}, 保存比例={frozen_scale.save_scale:g}")
                websocket_server.notify_scale_state("round_finished")

                # 获取该工位的数据段（两段拼接）
                # 第一段: start_sample (0) ~ first_end_sample
                t1, data1 = shared_daq.get_data_slice(self.name, self.start_sample, self.first_end_sample)
                t1, data1 = np.array(t1, copy=True), np.array(data1, copy=True)
                # 第二段: second_start_sample ~ stop_sample
                t2, data2 = shared_daq.get_data_slice(self.name, self.second_start_sample, self.stop_sample)
                t2, data2 = np.array(t2, copy=True), np.array(data2, copy=True)
                # 在推理/人工等待前脱离共享采集缓存，整轮及分段保存共用稳定的原始快照。
                for values in (t1, data1, t2, data2):
                    values.setflags(write=False)

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

                if t.size == 0:
                    print(f"[{self.name}] 无数据")
                    # 已在 900 关闭轮次；无数据不进入保存，不遗留 collecting 状态。
                    websocket_server.notify_scale_state("round_no_data")
                    self.plc.write_result(self.name, 2)
                    self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                    self.state = PC_STATUS_IDLE
                    continue

                t.setflags(write=False)
                data.setflags(write=False)
                # 推理仍使用原始值；缩放只在原始 CSV 成功保存后作用于 T2 自己的副本。
                label, score = self._do_inference(data)

                # 写入结果
                result_code = 1 if label == 0 else 2
                self.plc.write_result(self.name, result_code)
                print(f"[{self.name}] 结果已写入: {result_code}")

                # 回复完成
                self.plc.write_pc_status(self.name, PC_STATUS_COMPLETE)
                self.state = PC_STATUS_IDLE

                saved = self._save_round_data(t, data, t1, data1, t2, data2, label, frozen_scale)
                if saved.original_saved:
                    print(f"[{self.name}] 处理完成（原始已保存；副本状态={saved.scaled.status}）\n")
                else:
                    print(f"[{self.name}] 本轮保存不完整：原始训练 CSV 保存失败\n")
                # 清空WebSocket缓冲（只清空本工位）
                websocket_server.clear_buffer(self.name)

            except Exception as e:
                self._abort_scale_round("worker_error")
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

        self._abort_scale_round("worker_stopped")
        print(f"[{self.name}] 线程退出")
