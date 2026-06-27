import nidaqmx
import numpy as np
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.constants import TerminalConfiguration, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading

class DataAcquisition:
    def __init__(self, accel_channels, voltage_channel, current_channel,
                 sample_rate, chunk_samples, max_collect_time,
                 accel_range=(-50.0, 50.0), sensitivity=100,
                 sensor_output_max=10.0, voltage_sensor_max=36.0, current_sensor_max=30.0,
                 data_callback=None):
        """
        accel_channels: 加速度计通道字符串，如 "cDAQ1Mod1/ai0:2" (3通道 x,y,z)
        voltage_channel: 电压通道，如 "cDAQ1Mod3/ai0" (单通道)
        current_channel: 电流通道，如 "cDAQ1Mod3/ai2" (单通道)
        data_callback: 每采集一块数据时调用 callback(t_chunk, data_chunk)
                       data_chunk shape: (5, samples) 顺序为 [accel_x, accel_y, accel_z, voltage, current]
        """
        self.sr = sample_rate
        self.chunk = chunk_samples
        self.accel_ch = accel_channels
        self.voltage_ch = voltage_channel
        self.current_ch = current_channel
        self.accel_range = accel_range
        self.sensitivity = sensitivity
        self.sensor_output_max = sensor_output_max
        self.voltage_sensor_max = voltage_sensor_max
        self.current_sensor_max = current_sensor_max
        self.max_samples = int(self.sr * max_collect_time)
        self.data_callback = data_callback

        self.is_running = False
        self.thread = None
        self.full_t = None
        self.full_data = None   # 5通道: [x, y, z, voltage, current]
        self.sample_count = 0

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.full_t = np.empty(self.max_samples, dtype=np.float64)
        self.full_data = np.empty((5, self.max_samples), dtype=np.float64)  # 5通道
        self.sample_count = 0
        self.thread = threading.Thread(target=self._acq_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """停止采集，返回完整数据 (时间序列, 5×N数组)"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)

        # 如果从未采集数据，返回空数组
        if self.full_data is None or self.sample_count == 0:
            print("[采集] 警告: 没有采集到任何数据")
            return np.array([]), np.empty((5, 0))

        return self.full_t[:self.sample_count], self.full_data[:, :self.sample_count]

    def _acq_loop(self):
        task = nidaqmx.Task()
        try:
            # ----- 9234 加速度计 (3通道 x, y, z) -----
            task.ai_channels.add_ai_accel_chan(
                self.accel_ch,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )

            # ----- 9239 电压 (单通道) -----
            task.ai_channels.add_ai_voltage_chan(
                self.voltage_ch,
                min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS,
                terminal_config=TerminalConfiguration.DIFF
            )

            # ----- 9239 电流 (单通道) -----
            task.ai_channels.add_ai_voltage_chan(
                self.current_ch,
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
            buffer_all = np.zeros((5, self.chunk), dtype=np.float64)  # 5通道

            task.start()

            while self.is_running and self.sample_count < self.max_samples:
                try:
                    reader.read_many_sample(buffer_all, self.chunk, timeout=0.5)
                except nidaqmx.errors.DaqError as e:
                    if "timeout" in str(e):
                        continue
                    else:
                        raise

                start = self.sample_count
                end = start + self.chunk
                if end > self.max_samples:
                    end = self.max_samples
                    actual = end - start
                    t_chunk = np.linspace(start/self.sr, end/self.sr, actual, endpoint=False)
                    # 前3通道加速度，第4通道电压，第5通道电流
                    data_chunk = buffer_all[:, :actual]
                    # 换算电压和电流
                    converted_data = self._convert_data(data_chunk)
                    self.full_data[:, start:end] = converted_data
                    self.sample_count = end
                    self.full_t[start:end] = t_chunk
                    if self.data_callback:
                        self.data_callback(t_chunk, converted_data)
                    break
                else:
                    t_chunk = np.linspace(start/self.sr, end/self.sr, self.chunk, endpoint=False)
                    data_chunk = buffer_all.copy()
                    # 换算电压和电流
                    converted_data = self._convert_data(data_chunk)
                    self.full_data[:, start:end] = converted_data
                    self.sample_count = end
                    self.full_t[start:end] = t_chunk
                    if self.data_callback:
                        self.data_callback(t_chunk, converted_data)

        except Exception as e:
            print(f"[采集] 错误: {e}")
        finally:
            task.close()

    def _convert_data(self, data_chunk):
        """
        将原始数据转换为实际物理值
        data_chunk: (5, samples) [accel_x, accel_y, accel_z, raw_voltage, raw_current]
        返回: (5, samples) [accel_x, accel_y, accel_z, voltage, current]
        """
        converted = data_chunk.copy()
        # 加速度已经是物理值 (m/s²)，不需要转换
        # 电压换算
        converted[3, :] = data_chunk[3, :] / self.sensor_output_max * self.voltage_sensor_max
        # 电流换算
        converted[4, :] = data_chunk[4, :] / self.sensor_output_max * self.current_sensor_max
        return converted