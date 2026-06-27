import nidaqmx
import numpy as np
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.constants import TerminalConfiguration, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading
import time


class SharedDataAcquisition:
    """
    共享数据采集 - 同时采集左右工位所有通道
    左工位: cDAQ1Mod1/ai0:2 (3通道), cDAQ1Mod3/ai0 (电压), cDAQ1Mod3/ai2 (电流)
    右工位: cDAQ1Mod2/ai0:2 (3通道), cDAQ1Mod3/ai1 (电压), cDAQ1Mod3/ai3 (电流)
    """
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

        # 配置参数
        self.sr = 4800
        self.chunk = 1000
        self.max_collect_time = 60.0
        self.max_samples = int(self.sr * self.max_collect_time)

        # 通道配置
        self.left_accel = "cDAQ1Mod1/ai0:2"
        self.right_accel = "cDAQ1Mod2/ai0:2"
        self.left_voltage = "cDAQ1Mod3/ai0"
        self.right_voltage = "cDAQ1Mod3/ai1"
        self.left_current = "cDAQ1Mod3/ai2"
        self.right_current = "cDAQ1Mod3/ai3"

        # 传感器换算参数
        self.sensor_output_max = 10.0
        self.voltage_sensor_max = 36.0
        self.current_sensor_max = 30.0
        self.accel_range = (-50.0, 50.0)
        self.sensitivity = 100

        # 数据缓存
        self.left_data = None
        self.right_data = None
        self.left_t = None
        self.right_t = None
        self.sample_count = 0

        # 状态
        self.is_running = False
        self.thread = None
        self.callbacks = {"left": None, "right": None}

        print("[共享采集] 初始化完成")

    def register_callback(self, side, callback):
        """注册工位的数据回调"""
        self.callbacks[side] = callback
        print(f"[共享采集] 注册 {side} 回调")

    def start(self):
        """启动共享采集"""
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
        """停止采集"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=3.0)
        print(f"[共享采集] 采集已停止, 共采集 {self.sample_count} 个样本")

    def get_left_data(self):
        """获取左工位数据"""
        if self.left_data is None or self.sample_count == 0:
            return np.array([]), np.empty((5, 0))
        return self.left_t[:self.sample_count], self.left_data[:, :self.sample_count]

    def get_right_data(self):
        """获取右工位数据"""
        if self.right_data is None or self.sample_count == 0:
            return np.array([]), np.empty((5, 0))
        return self.right_t[:self.sample_count], self.right_data[:, :self.sample_count]

    def _convert_data(self, data_chunk, side):
        """
        将原始数据转换为实际物理值
        data_chunk: (samples, channels) 顺序:
            [left_accel_x, left_accel_y, left_accel_z,
             right_accel_x, right_accel_y, right_accel_z,
             left_voltage, right_voltage, left_current, right_current]
        """
        if side == "left":
            # 左工位: 3个加速度 + 电压 + 电流
            converted = np.zeros((5, data_chunk.shape[0]), dtype=np.float64)
            converted[0, :] = data_chunk[:, 0]  # x
            converted[1, :] = data_chunk[:, 1]  # y
            converted[2, :] = data_chunk[:, 2]  # z
            converted[3, :] = data_chunk[:, 6] / self.sensor_output_max * self.voltage_sensor_max  # 电压
            converted[4, :] = data_chunk[:, 8] / self.sensor_output_max * self.current_sensor_max  # 电流
            return converted
        else:
            # 右工位: 3个加速度 + 电压 + 电流
            converted = np.zeros((5, data_chunk.shape[0]), dtype=np.float64)
            converted[0, :] = data_chunk[:, 3]  # x
            converted[1, :] = data_chunk[:, 4]  # y
            converted[2, :] = data_chunk[:, 5]  # z
            converted[3, :] = data_chunk[:, 7] / self.sensor_output_max * self.voltage_sensor_max  # 电压
            converted[4, :] = data_chunk[:, 9] / self.sensor_output_max * self.current_sensor_max  # 电流
            return converted

    def _acq_loop(self):
        task = nidaqmx.Task()
        try:
            # ----- 左工位 9234 加速度计 (3通道 x, y, z) -----
            task.ai_channels.add_ai_accel_chan(
                self.left_accel,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )

            # ----- 右工位 9234 加速度计 (3通道 x, y, z) -----
            task.ai_channels.add_ai_accel_chan(
                self.right_accel,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )

            # ----- 9239 电压 (左工位) -----
            task.ai_channels.add_ai_voltage_chan(
                self.left_voltage,
                min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS,
                terminal_config=TerminalConfiguration.DIFF
            )

            # ----- 9239 电压 (右工位) -----
            task.ai_channels.add_ai_voltage_chan(
                self.right_voltage,
                min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS,
                terminal_config=TerminalConfiguration.DIFF
            )

            # ----- 9239 电流 (左工位) -----
            task.ai_channels.add_ai_voltage_chan(
                self.left_current,
                min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS,
                terminal_config=TerminalConfiguration.DIFF
            )

            # ----- 9239 电流 (右工位) -----
            task.ai_channels.add_ai_voltage_chan(
                self.right_current,
                min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS,
                terminal_config=TerminalConfiguration.DIFF
            )

            # ----- 配置采样 -----
            task.timing.cfg_samp_clk_timing(
                self.sr,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self.chunk * 2
            )
            task.in_stream.input_buf_size = 1000000

            reader = AnalogMultiChannelReader(task.in_stream)
            buffer_all = np.zeros((10, self.chunk), dtype=np.float64)  # 10通道

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

                    # 提取数据 (转置为 [samples, channels])
                    data_block = buffer_all[:, :actual].T

                    # 左工位数据
                    left_converted = self._convert_data(data_block, "left")
                    self.left_data[:, start:end] = left_converted
                    self.left_t[start:end] = t_chunk
                    if self.callbacks["left"]:
                        self.callbacks["left"](t_chunk, left_converted)

                    # 右工位数据
                    right_converted = self._convert_data(data_block, "right")
                    self.right_data[:, start:end] = right_converted
                    self.right_t[start:end] = t_chunk
                    if self.callbacks["right"]:
                        self.callbacks["right"](t_chunk, right_converted)

                    self.sample_count = end
                    break
                else:
                    t_chunk = np.linspace(start / self.sr, end / self.sr, self.chunk, endpoint=False)

                    # 提取数据 (转置为 [samples, channels])
                    data_block = buffer_all[:, :].T

                    # 左工位数据
                    left_converted = self._convert_data(data_block, "left")
                    self.left_data[:, start:end] = left_converted
                    self.left_t[start:end] = t_chunk
                    if self.callbacks["left"]:
                        self.callbacks["left"](t_chunk, left_converted)

                    # 右工位数据
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


# 全局共享实例
shared_daq = SharedDataAcquisition()