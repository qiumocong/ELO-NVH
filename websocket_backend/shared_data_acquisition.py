import nidaqmx
import numpy as np
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.constants import TerminalConfiguration, VoltageUnits, CurrentUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading
import time
from config import (
    STATIONS, SAMPLE_RATE, CHUNK_SAMPLES, MAX_COLLECT_TIME,
    RANGE_9234, SENSITIVITY, SENSOR_OUTPUT_MAX,
    VOLTAGE_SENSOR_MAX, CURRENT_SENSOR_MAX, DAQ_ADD_ORDER
)

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

        # 从 config 读取通道
        self.left_accel = STATIONS["left"]["accel_channels"]
        self.right_accel = STATIONS["right"]["accel_channels"]
        self.left_voltage = STATIONS["left"]["voltage_channel"]
        self.right_voltage = STATIONS["right"]["voltage_channel"]
        self.left_current = STATIONS["left"]["current_channel"]
        self.right_current = STATIONS["right"]["current_channel"]

        self.sensor_output_max = SENSOR_OUTPUT_MAX
        self.voltage_sensor_max = VOLTAGE_SENSOR_MAX
        self.current_sensor_max = CURRENT_SENSOR_MAX
        self.accel_range = RANGE_9234
        self.sensitivity = SENSITIVITY

        self.left_data = None
        self.right_data = None
        self.left_t = None
        self.right_t = None
        self.sample_count = 0

        self.is_running = False
        self.thread = None
        self.callbacks = {"left": None, "right": None}

        print("[共享采集] 初始化完成")

    def register_callback(self, side, callback):
        self.callbacks[side] = callback
        print(f"[共享采集] 注册 {side} 回调")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.sample_count = 0
        self.left_data = np.empty((5, self.max_samples), dtype=np.float64)
        self.right_data = np.empty((5, self.max_samples), dtype=np.float64)
        self.left_t = np.empty(self.max_samples, dtype=np.float64)
        self.right_t = np.empty(self.max_samples, dtype=np.float64)
        self.thread = threading.Thread(target=self._acq_loop, daemon=True)
        self.thread.start()
        print("[共享采集] 采集已启动")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=3.0)
        print(f"[共享采集] 采集已停止, 共采集 {self.sample_count} 个样本")

    def get_left_data(self):
        if self.left_data is None or self.sample_count == 0:
            return np.array([]), np.empty((5, 0))
        return self.left_t[:self.sample_count], self.left_data[:, :self.sample_count]

    def get_right_data(self):
        if self.right_data is None or self.sample_count == 0:
            return np.array([]), np.empty((5, 0))
        return self.right_t[:self.sample_count], self.right_data[:, :self.sample_count]

    def _convert_data(self, data_chunk, side):
        """
        data_chunk: (samples, 10) 顺序由添加顺序决定：
        0-2: left accel, 3-5: right accel, 6: left voltage, 7: right voltage, 8: left current, 9: right current
        """
        if side == "left":
            converted = np.zeros((5, data_chunk.shape[0]), dtype=np.float64)
            converted[0, :] = data_chunk[:, 0]  # x
            converted[1, :] = data_chunk[:, 1]  # y
            converted[2, :] = data_chunk[:, 2]  # z
            converted[3, :] = data_chunk[:, 6] / self.sensor_output_max * self.voltage_sensor_max
            converted[4, :] = data_chunk[:, 8] / self.sensor_output_max * self.current_sensor_max
            return converted
        else:
            converted = np.zeros((5, data_chunk.shape[0]), dtype=np.float64)
            converted[0, :] = data_chunk[:, 3]  # x
            converted[1, :] = data_chunk[:, 4]  # y
            converted[2, :] = data_chunk[:, 5]  # z
            converted[3, :] = data_chunk[:, 7] / self.sensor_output_max * self.voltage_sensor_max
            converted[4, :] = data_chunk[:, 9] / self.sensor_output_max * self.current_sensor_max
            return converted

    def _acq_loop(self):
        task = nidaqmx.Task()
        try:
            # 按 DAQ_ADD_ORDER 添加通道，保证索引固定
            # 1. 左加速度
            task.ai_channels.add_ai_accel_chan(
                self.left_accel,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )
            # 2. 右加速度
            task.ai_channels.add_ai_accel_chan(
                self.right_accel,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )
            # 3. 左电压（AI2）
            task.ai_channels.add_ai_voltage_chan(
                self.left_voltage,
                min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS,
                terminal_config=TerminalConfiguration.DIFF
            )
            # 4. 右电压（AI0）
            task.ai_channels.add_ai_voltage_chan(
                self.right_voltage,
                min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS,
                terminal_config=TerminalConfiguration.DIFF
            )
            # 5. 左电流（AI3）
            task.ai_channels.add_ai_current_chan(
                self.left_current,
                min_val=0.0, max_val=self.sensor_output_max,
                units=CurrentUnits.AMPS,
                terminal_config=TerminalConfiguration.DIFF
            )
            # 6. 右电流（AI1）
            task.ai_channels.add_ai_current_chan(
                self.right_current,
                min_val=0.0, max_val=self.sensor_output_max,
                units=CurrentUnits.AMPS,
                terminal_config=TerminalConfiguration.DIFF
            )

            task.timing.cfg_samp_clk_timing(
                self.sr,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self.chunk * 2
            )
            task.in_stream.input_buf_size = 1000000

            reader = AnalogMultiChannelReader(task.in_stream)
            buffer_all = np.zeros((10, self.chunk), dtype=np.float64)   # 10通道

            task.start()
            print("[共享采集] NI任务已启动，10通道同时采集")

            while self.is_running and self.sample_count < self.max_samples:
                try:
                    reader.read_many_sample(buffer_all, self.chunk, timeout=1.0)
                except nidaqmx.errors.DaqError as e:
                    if "timeout" in str(e):
                        continue
                    else:
                        print(f"[共享采集] 读取错误: {e}")
                        break

                start = self.sample_count
                end = start + self.chunk
                if end > self.max_samples:
                    end = self.max_samples
                    actual = end - start
                    t_chunk = np.linspace(start / self.sr, end / self.sr, actual, endpoint=False)
                    data_block = buffer_all[:, :actual].T

                    left_converted = self._convert_data(data_block, "left")
                    self.left_data[:, start:end] = left_converted
                    self.left_t[start:end] = t_chunk
                    if self.callbacks["left"]:
                        self.callbacks["left"](t_chunk, left_converted)

                    right_converted = self._convert_data(data_block, "right")
                    self.right_data[:, start:end] = right_converted
                    self.right_t[start:end] = t_chunk
                    if self.callbacks["right"]:
                        self.callbacks["right"](t_chunk, right_converted)

                    self.sample_count = end
                    break
                else:
                    t_chunk = np.linspace(start / self.sr, end / self.sr, self.chunk, endpoint=False)
                    data_block = buffer_all[:, :].T

                    left_converted = self._convert_data(data_block, "left")
                    self.left_data[:, start:end] = left_converted
                    self.left_t[start:end] = t_chunk
                    if self.callbacks["left"]:
                        self.callbacks["left"](t_chunk, left_converted)

                    right_converted = self._convert_data(data_block, "right")
                    self.right_data[:, start:end] = right_converted
                    self.right_t[start:end] = t_chunk
                    if self.callbacks["right"]:
                        self.callbacks["right"](t_chunk, right_converted)

                    self.sample_count = end

        except Exception as e:
            print(f"[共享采集] 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                task.stop()
                task.close()
            except:
                pass
            print("[共享采集] NI任务已关闭")

shared_daq = SharedDataAcquisition()