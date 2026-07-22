import nidaqmx
import numpy as np
import time
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.constants import TerminalConfiguration, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading
from config import STATIONS, SAMPLE_RATE, CHUNK_SAMPLES, MAX_COLLECT_TIME
from config import RANGE_9234, SENSITIVITY, SENSOR_OUTPUT_MAX
from config import VOLTAGE_SENSOR_MAX, CURRENT_SENSOR_MAX, START_DELAY


class SharedDataAcquisition:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.sr = SAMPLE_RATE
        self.chunk = CHUNK_SAMPLES
        self.max_collect_time = MAX_COLLECT_TIME
        self.max_samples = int(self.sr * self.max_collect_time)

        self.accel_range = RANGE_9234
        self.sensitivity = SENSITIVITY
        self.sensor_output_max = SENSOR_OUTPUT_MAX
        self.voltage_sensor_max = VOLTAGE_SENSOR_MAX
        self.current_sensor_max = CURRENT_SENSOR_MAX

        self.left_accel = STATIONS["left"]["accel_channels"]
        self.right_accel = STATIONS["right"]["accel_channels"]
        self.left_voltage = STATIONS["left"]["voltage_channel"]
        self.left_current = STATIONS["left"]["current_channel"]
        self.right_voltage = STATIONS["right"]["voltage_channel"]
        self.right_current = STATIONS["right"]["current_channel"]

        self.is_running = False
        self._stop_requested = False
        self.thread = None
        self.callbacks = {"left": None, "right": None}

        # ---- 左右工位独立状态 ----
        self.left_sample_count = 0
        self.right_sample_count = 0
        self.left_data = None
        self.right_data = None
        self.left_t = None
        self.right_t = None
        self.left_has_data = False
        self.right_has_data = False

        # 延迟相关
        self.left_delay_until = None
        self.right_delay_until = None
        self.left_recording = False
        self.right_recording = False
        self.left_start_sample = 0   # 记录开始时的样本索引（用于时间轴归零）
        self.right_start_sample = 0

        self.start_delay = START_DELAY

        print("[共享采集] 初始化完成（支持左右独立延迟）")
        print(f"  左加速度: {self.left_accel}")
        print(f"  右加速度: {self.right_accel}")
        print(f"  左电压: {self.left_voltage}, 左电流: {self.left_current}")
        print(f"  右电压: {self.right_voltage}, 右电流: {self.right_current}")

    def register_callback(self, side, callback):
        self.callbacks[side] = callback
        print(f"[共享采集] 注册 {side} 回调")

    def start_side(self, side, reset_time=True, enable_delay=True):
        """
        启动/重置某个工位的采集状态
        side: 'left' 或 'right'
        reset_time: 是否重置该工位的数据（清空历史）
        enable_delay: 是否启用延迟（仅 reset_time=True 时有效）
        """
        if side not in ("left", "right"):
            return

        # 如果采集任务未运行，先启动采集任务（只启动一次）
        if not self.is_running:
            self.is_running = True
            self._stop_requested = False
            self.thread = threading.Thread(target=self._acq_loop, daemon=True)
            self.thread.start()
            # 稍等线程启动
            time.sleep(0.2)

        # 重置该工位的数据
        if reset_time:
            if side == "left":
                self.left_sample_count = 0
                self.left_has_data = False
                self.left_data = np.empty((5, self.max_samples), dtype=np.float64)
                self.left_t = np.empty(self.max_samples, dtype=np.float64)
                if enable_delay:
                    self.left_delay_until = time.time() + self.start_delay
                    self.left_recording = False
                else:
                    self.left_delay_until = None
                    self.left_recording = True
                self.left_start_sample = 0
            else:  # right
                self.right_sample_count = 0
                self.right_has_data = False
                self.right_data = np.empty((5, self.max_samples), dtype=np.float64)
                self.right_t = np.empty(self.max_samples, dtype=np.float64)
                if enable_delay:
                    self.right_delay_until = time.time() + self.start_delay
                    self.right_recording = False
                else:
                    self.right_delay_until = None
                    self.right_recording = True
                self.right_start_sample = 0
        else:
            # 不重置，时间连续（不启用延迟）
            if side == "left":
                self.left_delay_until = None
                self.left_recording = True
            else:
                self.right_delay_until = None
                self.right_recording = True

        delay_msg = f"延迟 {self.start_delay}s" if (side == "left" and self.left_delay_until) or (side == "right" and self.right_delay_until) else "无延迟"
        print(f"[共享采集] {side} 工位启动{' (重置)' if reset_time else ' (连续)'}，{delay_msg}")

    def stop(self):
        print("[共享采集] 收到停止请求...")
        self._stop_requested = True
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print(f"[共享采集] 采集已停止")

    def get_data_slice(self, side, start_idx, end_idx):
        """
        获取指定工位的样本切片
        side: 'left' 或 'right'
        start_idx, end_idx: 该工位独立样本索引
        """
        if side == "left":
            count = self.left_sample_count
            t = self.left_t
            data = self.left_data
        else:
            count = self.right_sample_count
            t = self.right_t
            data = self.right_data

        if data is None or count == 0:
            return np.array([]), np.empty((5, 0))

        start_idx = max(0, start_idx)
        end_idx = min(count, end_idx)
        if start_idx >= end_idx:
            return np.array([]), np.empty((5, 0))

        return t[start_idx:end_idx], data[:, start_idx:end_idx]

    def get_left_data(self):
        if self.left_data is None or self.left_sample_count == 0 or not self.left_has_data:
            return np.array([]), np.empty((5, 0))
        return self.left_t[:self.left_sample_count], self.left_data[:, :self.left_sample_count]

    def get_right_data(self):
        if self.right_data is None or self.right_sample_count == 0 or not self.right_has_data:
            return np.array([]), np.empty((5, 0))
        return self.right_t[:self.right_sample_count], self.right_data[:, :self.right_sample_count]

    def _convert_data(self, data_block, side):
        """
        data_block: (samples, 5) 顺序 [x, y, z, raw_voltage, raw_current]
        返回 (5, samples) 实际物理值
        """
        converted = np.zeros((5, data_block.shape[0]), dtype=np.float64)
        converted[0, :] = data_block[:, 0]  # x
        converted[1, :] = data_block[:, 1]  # y
        converted[2, :] = data_block[:, 2]  # z
        converted[3, :] = data_block[:, 3] / self.sensor_output_max * self.voltage_sensor_max
        converted[4, :] = data_block[:, 4] / self.sensor_output_max * self.current_sensor_max
        return converted

    def _acq_loop(self):
        task = None
        try:
            task = nidaqmx.Task()

            task.ai_channels.add_ai_accel_chan(
                self.left_accel,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )
            task.ai_channels.add_ai_accel_chan(
                self.right_accel,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )

            # 按顺序：右电压、右电流、左电压、左电流
            task.ai_channels.add_ai_voltage_chan(
                self.right_voltage, min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS, terminal_config=TerminalConfiguration.DIFF
            )
            task.ai_channels.add_ai_voltage_chan(
                self.right_current, min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS, terminal_config=TerminalConfiguration.DIFF
            )
            task.ai_channels.add_ai_voltage_chan(
                self.left_voltage, min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS, terminal_config=TerminalConfiguration.DIFF
            )
            task.ai_channels.add_ai_voltage_chan(
                self.left_current, min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS, terminal_config=TerminalConfiguration.DIFF
            )

            task.timing.cfg_samp_clk_timing(
                self.sr, sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self.chunk * 2
            )
            task.in_stream.input_buf_size = 1000000
            reader = AnalogMultiChannelReader(task.in_stream)
            buffer_all = np.zeros((10, self.chunk), dtype=np.float64)

            task.start()
            actual_rate = task.timing.samp_clk_rate
            print(f"[共享采集] NI任务已启动，10通道同时采集")
            print(f"[共享采集] 实际采样时钟: {actual_rate} Hz (配置: {self.sr})")

            start_time = time.time()

            while self.is_running:
                if self._stop_requested:
                    print("[共享采集] 检测到停止请求，退出采集循环")
                    break

                try:
                    reader.read_many_sample(buffer_all, self.chunk, timeout=0.5)
                except nidaqmx.errors.DaqError as e:
                    if "timeout" in str(e):
                        if self._stop_requested:
                            break
                        time.sleep(0.01)
                        continue
                    else:
                        print(f"[共享采集] 读取错误: {e}")
                        break

                # ---- 处理左侧数据 ----
                if not self._process_side("left", buffer_all, self.chunk):
                    break

                # ---- 处理右侧数据 ----
                if not self._process_side("right", buffer_all, self.chunk):
                    break

                time.sleep(0.002)

            elapsed = time.time() - start_time
            print(f"[共享采集] 采集循环结束 ({elapsed:.2f}s)")

        except Exception as e:
            print(f"[共享采集] 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if task:
                try:
                    task.stop()
                    task.close()
                except:
                    pass
            self.is_running = False
            print("[共享采集] NI任务已关闭")

    def get_sample_count(self, side):
        if side == "left":
            return self.left_sample_count
        else:
            return self.right_sample_count

    def _process_side(self, side, buffer_all, chunk_samples):
        """
        处理单个工位的数据，包含延迟判断和存储
        返回 False 表示应退出循环
        """
        # 确定该工位的状态
        if side == "left":
            delay_until = self.left_delay_until
            recording = self.left_recording
            sample_count = self.left_sample_count
            t_array = self.left_t
            data_array = self.left_data
            has_data = self.left_has_data
            callback = self.callbacks["left"]
            start_sample = self.left_start_sample
            max_samples = self.max_samples
        else:
            delay_until = self.right_delay_until
            recording = self.right_recording
            sample_count = self.right_sample_count
            t_array = self.right_t
            data_array = self.right_data
            has_data = self.right_has_data
            callback = self.callbacks["right"]
            start_sample = self.right_start_sample
            max_samples = self.max_samples

        # 如果该工位数据未初始化，跳过（可能尚未调用 start_side）
        if data_array is None:
            return True

        # 延迟检测
        if delay_until is not None and not recording:
            now = time.time()
            if now < delay_until:
                # 未到记录时间，丢弃数据
                return True
            else:
                # 延迟结束，开始记录
                recording = True
                if side == "left":
                    self.left_recording = True
                    self.left_delay_until = None
                    self.left_start_sample = 0  # 从0开始
                    print("[共享采集] 左工位开始记录数据")
                else:
                    self.right_recording = True
                    self.right_delay_until = None
                    self.right_start_sample = 0
                    print("[共享采集] 右工位开始记录数据")
                # 重置该工位的计数
                sample_count = 0

        # 如果该工位尚未开始记录，跳过存储
        if not recording:
            return True

        # 开始存储数据
        # 提取该工位的数据块（从 buffer_all 中提取对应列）
        # 注意 buffer_all 顺序：前3左加速，3-5右加速，6右电压，7右电流，8左电压，9左电流
        if side == "left":
            # 左加速：0,1,2；左电压：8；左电流：9
            left_block = np.vstack([
                buffer_all[0:3, :],   # x,y,z
                buffer_all[8:10, :]   # voltage, current
            ]).T  # shape (chunk, 5)
            data_block = left_block
        else:
            # 右加速：3,4,5；右电压：6；右电流：7
            right_block = np.vstack([
                buffer_all[3:6, :],
                buffer_all[6:8, :]
            ]).T  # shape (chunk, 5)
            data_block = right_block

        # 转换物理值
        converted = self._convert_data(data_block, side)  # shape (5, chunk)

        # 计算当前块的长度
        block_len = converted.shape[1]
        if sample_count + block_len > max_samples:
            # 超出最大长度，只取剩余部分
            remain = max_samples - sample_count
            if remain <= 0:
                return True
            converted = converted[:, :remain]
            block_len = remain

        # 生成时间轴（相对于该工位的起始）
        t_chunk = np.linspace(sample_count / self.sr, (sample_count + block_len) / self.sr, block_len, endpoint=False)

        # 存储数据
        start_idx = sample_count
        end_idx = sample_count + block_len
        data_array[:, start_idx:end_idx] = converted
        t_array[start_idx:end_idx] = t_chunk

        # 更新该工位的计数和状态
        if side == "left":
            self.left_sample_count = end_idx
            self.left_has_data = True
            if callback:
                callback(t_chunk, converted)
        else:
            self.right_sample_count = end_idx
            self.right_has_data = True
            if callback:
                callback(t_chunk, converted)

        return True

shared_daq = SharedDataAcquisition()