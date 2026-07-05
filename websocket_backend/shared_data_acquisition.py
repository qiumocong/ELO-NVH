import nidaqmx
import numpy as np
import time
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.constants import TerminalConfiguration, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading
from config import STATIONS, SAMPLE_RATE, CHUNK_SAMPLES, MAX_COLLECT_TIME
from config import RANGE_9234, SENSITIVITY, SENSOR_OUTPUT_MAX
from config import VOLTAGE_SENSOR_MAX, CURRENT_SENSOR_MAX

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
        self.sample_count = 0

        self.left_data = None
        self.right_data = None
        self.left_t = None
        self.right_t = None
        self.left_has_data = False
        self.right_has_data = False

        print("[共享采集] 初始化完成")
        print(f"  左加速度: {self.left_accel}")
        print(f"  右加速度: {self.right_accel}")
        print(f"  左电压: {self.left_voltage}, 左电流: {self.left_current}")
        print(f"  右电压: {self.right_voltage}, 右电流: {self.right_current}")

    def register_callback(self, side, callback):
        self.callbacks[side] = callback
        print(f"[共享采集] 注册 {side} 回调")

    def start(self, reset_time=True):
        if self.is_running:
            return
        if reset_time:
            self.sample_count = 0
            self.left_has_data = False
            self.right_has_data = False
            self.left_data = np.empty((5, self.max_samples), dtype=np.float64)
            self.right_data = np.empty((5, self.max_samples), dtype=np.float64)
            self.left_t = np.empty(self.max_samples, dtype=np.float64)
            self.right_t = np.empty(self.max_samples, dtype=np.float64)
        self.is_running = True
        self._stop_requested = False
        self.thread = threading.Thread(target=self._acq_loop, daemon=True)
        self.thread.start()
        print("[共享采集] 采集已启动" + (" (时间重置)" if reset_time else " (时间连续)"))

    def stop(self):
        print("[共享采集] 收到停止请求...")
        self._stop_requested = True
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print(f"[共享采集] 采集已停止, 共采集 {self.sample_count} 个样本 ({self.sample_count / self.sr:.2f}s)")

    def get_data_slice(self, side, start_idx, end_idx):
        """
        获取指定样本范围的数据
        start_idx, end_idx: 样本索引（整数）
        返回 (t, data) 其中 t 为时间数组，data 形状 (5, n)
        """
        if start_idx < 0:
            start_idx = 0
        if end_idx > self.sample_count:
            end_idx = self.sample_count
        if start_idx >= end_idx:
            return np.array([]), np.empty((5, 0))
        if side == "left":
            t = self.left_t[start_idx:end_idx]
            data = self.left_data[:, start_idx:end_idx]
        else:
            t = self.right_t[start_idx:end_idx]
            data = self.right_data[:, start_idx:end_idx]
        return t, data

    def get_left_data(self):
        if self.left_data is None or self.sample_count == 0 or not self.left_has_data:
            return np.array([]), np.empty((5, 0))
        return self.left_t[:self.sample_count], self.left_data[:, :self.sample_count]

    def get_right_data(self):
        if self.right_data is None or self.sample_count == 0 or not self.right_has_data:
            return np.array([]), np.empty((5, 0))
        return self.right_t[:self.sample_count], self.right_data[:, :self.sample_count]

    def _convert_data(self, data_block, side):
        converted = np.zeros((5, data_block.shape[0]), dtype=np.float64)
        if side == "left":
            converted[0, :] = data_block[:, 0]
            converted[1, :] = data_block[:, 1]
            converted[2, :] = data_block[:, 2]
            converted[3, :] = data_block[:, 8] / self.sensor_output_max * self.voltage_sensor_max
            converted[4, :] = data_block[:, 9] / self.sensor_output_max * self.current_sensor_max
        else:
            converted[0, :] = data_block[:, 3]
            converted[1, :] = data_block[:, 4]
            converted[2, :] = data_block[:, 5]
            converted[3, :] = data_block[:, 6] / self.sensor_output_max * self.voltage_sensor_max
            converted[4, :] = data_block[:, 7] / self.sensor_output_max * self.current_sensor_max
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
                current_excit_val=0.004,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )
            task.ai_channels.add_ai_accel_chan(
                self.right_accel,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.004,
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
            print("[共享采集] NI任务已启动，10通道同时采集")
            start_time = time.time()

            while self.is_running and self.sample_count < self.max_samples:
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

                start = self.sample_count
                end = start + self.chunk
                if end > self.max_samples:
                    end = self.max_samples
                    actual = end - start
                    if actual <= 0:
                        break
                    t_chunk = np.linspace(start / self.sr, end / self.sr, actual, endpoint=False)
                    data_block = buffer_all[:, :actual].T

                    left_data = self._convert_data(data_block, "left")
                    right_data = self._convert_data(data_block, "right")

                    if np.any(left_data != 0):
                        self.left_has_data = True
                    if np.any(right_data != 0):
                        self.right_has_data = True

                    self.left_data[:, start:end] = left_data
                    self.right_data[:, start:end] = right_data
                    self.left_t[start:end] = t_chunk
                    self.right_t[start:end] = t_chunk

                    if self.callbacks["left"] and self.left_has_data:
                        self.callbacks["left"](t_chunk, left_data)
                    if self.callbacks["right"] and self.right_has_data:
                        self.callbacks["right"](t_chunk, right_data)

                    self.sample_count = end
                    break
                else:
                    t_chunk = np.linspace(start / self.sr, end / self.sr, self.chunk, endpoint=False)
                    data_block = buffer_all[:, :].T

                    left_data = self._convert_data(data_block, "left")
                    right_data = self._convert_data(data_block, "right")

                    if np.any(left_data != 0):
                        self.left_has_data = True
                    if np.any(right_data != 0):
                        self.right_has_data = True

                    self.left_data[:, start:end] = left_data
                    self.right_data[:, start:end] = right_data
                    self.left_t[start:end] = t_chunk
                    self.right_t[start:end] = t_chunk

                    if self.callbacks["left"] and self.left_has_data:
                        self.callbacks["left"](t_chunk, left_data)
                    if self.callbacks["right"] and self.right_has_data:
                        self.callbacks["right"](t_chunk, right_data)

                    self.sample_count = end

                time.sleep(0.002)

            elapsed = time.time() - start_time
            print(f"[共享采集] 采集循环结束，实际采集 {self.sample_count} 个样本 ({elapsed:.2f}s)")

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

shared_daq = SharedDataAcquisition()