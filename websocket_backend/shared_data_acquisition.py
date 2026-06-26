import nidaqmx
import numpy as np
import time
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.constants import TerminalConfiguration, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading


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

        from config import SAMPLE_RATE, CHUNK_SAMPLES, MAX_COLLECT_TIME
        from config import RANGE_9234, SENSITIVITY, SENSOR_OUTPUT_MAX
        from config import VOLTAGE_SENSOR_MAX, CURRENT_SENSOR_MAX

        self.sr = SAMPLE_RATE
        self.chunk = CHUNK_SAMPLES
        self.max_collect_time = MAX_COLLECT_TIME
        self.max_samples = int(self.sr * self.max_collect_time)

        self.accel_range = RANGE_9234
        self.sensitivity = SENSITIVITY
        self.sensor_output_max = SENSOR_OUTPUT_MAX
        self.voltage_sensor_max = VOLTAGE_SENSOR_MAX
        self.current_sensor_max = CURRENT_SENSOR_MAX

        self.is_running = False
        self._stop_requested = False  # 新增：停止请求标志
        self.thread = None
        self.callbacks = {"left": None, "right": None}
        self.sample_count = 0

        self.left_data = None
        self.right_data = None
        self.left_t = None
        self.right_t = None

        print("[共享采集] 初始化完成")

    def register_callback(self, side, callback):
        self.callbacks[side] = callback
        print(f"[共享采集] 注册 {side} 回调")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._stop_requested = False
        self.sample_count = 0
        self.left_data = np.empty((5, self.max_samples), dtype=np.float64)
        self.right_data = np.empty((5, self.max_samples), dtype=np.float64)
        self.left_t = np.empty(self.max_samples, dtype=np.float64)
        self.right_t = np.empty(self.max_samples, dtype=np.float64)
        self.thread = threading.Thread(target=self._acq_loop, daemon=True)
        self.thread.start()
        print("[共享采集] 采集已启动")

    def stop(self):
        """停止采集"""
        print("[共享采集] 收到停止请求...")
        self._stop_requested = True
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print(f"[共享采集] 采集已停止, 共采集 {self.sample_count} 个样本 ({self.sample_count / self.sr:.2f}s)")

    def get_left_data(self):
        if self.left_data is None or self.sample_count == 0:
            return np.array([]), np.empty((5, 0))
        return self.left_t[:self.sample_count], self.left_data[:, :self.sample_count]

    def get_right_data(self):
        if self.right_data is None or self.sample_count == 0:
            return np.array([]), np.empty((5, 0))
        return self.right_t[:self.sample_count], self.right_data[:, :self.sample_count]

    def _convert_data(self, data_block, side):
        """data_block: [samples, 10 channels]"""
        converted = np.zeros((5, data_block.shape[0]), dtype=np.float64)
        if side == "left":
            converted[0, :] = data_block[:, 0]
            converted[1, :] = data_block[:, 1]
            converted[2, :] = data_block[:, 2]
            converted[3, :] = data_block[:, 6] / self.sensor_output_max * self.voltage_sensor_max
            converted[4, :] = data_block[:, 8] / self.sensor_output_max * self.current_sensor_max
        else:
            converted[0, :] = data_block[:, 3]
            converted[1, :] = data_block[:, 4]
            converted[2, :] = data_block[:, 5]
            converted[3, :] = data_block[:, 7] / self.sensor_output_max * self.voltage_sensor_max
            converted[4, :] = data_block[:, 9] / self.sensor_output_max * self.current_sensor_max
        return converted

    def _acq_loop(self):
        task = None
        try:
            task = nidaqmx.Task()

            # 左工位 9234
            task.ai_channels.add_ai_accel_chan(
                "cDAQ1Mod1/ai0:2",
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )

            # 右工位 9234
            task.ai_channels.add_ai_accel_chan(
                "cDAQ1Mod2/ai0:2",
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )

            # 9239 电压/电流
            channels = [
                ("cDAQ1Mod3/ai0", "电压_左"),
                ("cDAQ1Mod3/ai1", "电压_右"),
                ("cDAQ1Mod3/ai2", "电流_左"),
                ("cDAQ1Mod3/ai3", "电流_右"),
            ]
            for ch, name in channels:
                task.ai_channels.add_ai_voltage_chan(
                    ch, min_val=0.0, max_val=self.sensor_output_max,
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

            # 记录开始时间
            start_time = time.time()

            while self.is_running and self.sample_count < self.max_samples:
                # 检查停止请求
                if self._stop_requested:
                    print("[共享采集] 检测到停止请求，退出采集循环")
                    break

                try:
                    reader.read_many_sample(buffer_all, self.chunk, timeout=0.5)
                except nidaqmx.errors.DaqError as e:
                    if "timeout" in str(e):
                        # 超时时检查是否有停止请求
                        if self._stop_requested:
                            break
                        time.sleep(0.01)
                        continue
                    else:
                        print(f"[共享采集] 读取错误: {e}")
                        break

                start = self.sample_count
                end = start + self.chunk

                # 如果剩余空间不足，只取剩余部分
                if end > self.max_samples:
                    end = self.max_samples
                    actual = end - start
                    if actual <= 0:
                        break
                    t_chunk = np.linspace(start / self.sr, end / self.sr, actual, endpoint=False)
                    data_block = buffer_all[:, :actual].T

                    left_data = self._convert_data(data_block, "left")
                    right_data = self._convert_data(data_block, "right")

                    self.left_data[:, start:end] = left_data
                    self.right_data[:, start:end] = right_data
                    self.left_t[start:end] = t_chunk
                    self.right_t[start:end] = t_chunk

                    if self.callbacks["left"]:
                        self.callbacks["left"](t_chunk, left_data)
                    if self.callbacks["right"]:
                        self.callbacks["right"](t_chunk, right_data)

                    self.sample_count = end
                    break
                else:
                    t_chunk = np.linspace(start / self.sr, end / self.sr, self.chunk, endpoint=False)
                    data_block = buffer_all[:, :].T

                    left_data = self._convert_data(data_block, "left")
                    right_data = self._convert_data(data_block, "right")

                    self.left_data[:, start:end] = left_data
                    self.right_data[:, start:end] = right_data
                    self.left_t[start:end] = t_chunk
                    self.right_t[start:end] = t_chunk

                    if self.callbacks["left"]:
                        self.callbacks["left"](t_chunk, left_data)
                    if self.callbacks["right"]:
                        self.callbacks["right"](t_chunk, right_data)

                    self.sample_count = end

                # 每块数据后释放CPU，让PLC通信有机会执行
                time.sleep(0.002)

            # 计算实际采集时长
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