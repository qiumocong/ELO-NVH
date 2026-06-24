import nidaqmx
import numpy as np
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading

class DataAcquisition:
    def __init__(self, accel_channels, voltage_channels, sample_rate, chunk_samples, max_collect_time,
                 accel_range=(-50.0, 50.0), sensitivity=100, voltage_range=(-10.0, 10.0),
                 data_callback=None):
        """
        accel_channels: 加速度计通道字符串，如 "cDAQ1Mod1/ai0:1"
        voltage_channels: 电压通道字符串，如 "cDAQ1Mod2/ai0:1"
        data_callback: 每采集一块数据时调用 callback(t_chunk, data_chunk)
                       data_chunk shape: (total_channels, samples)
        """
        self.sr = sample_rate
        self.chunk = chunk_samples
        self.accel_ch = accel_channels
        self.voltage_ch = voltage_channels
        self.accel_range = accel_range
        self.sensitivity = sensitivity
        self.voltage_range = voltage_range
        self.max_samples = int(self.sr * max_collect_time)
        self.data_callback = data_callback

        self.is_running = False
        self.thread = None
        self.full_t = None
        self.full_data = None
        self.sample_count = 0

        # 解析通道数量
        def count_channels(ch_str):
            if ':' in ch_str:
                start, end = ch_str.split(':')
                start_num = int(''.join(filter(str.isdigit, start.split('/')[-1])))
                end_num = int(''.join(filter(str.isdigit, end)))
                return end_num - start_num + 1
            else:
                return 1
        self.num_accel = count_channels(self.accel_ch)
        self.num_voltage = count_channels(self.voltage_ch)
        self.total_channels = self.num_accel + self.num_voltage

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.full_t = np.empty(self.max_samples, dtype=np.float64)
        self.full_data = np.empty((self.total_channels, self.max_samples), dtype=np.float64)
        self.sample_count = 0
        self.thread = threading.Thread(target=self._acq_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        return self.full_t[:self.sample_count], self.full_data[:, :self.sample_count]

    def _acq_loop(self):
        task_accel = nidaqmx.Task()
        task_voltage = nidaqmx.Task()
        try:
            # 加速度计
            task_accel.ai_channels.add_ai_accel_chan(
                self.accel_ch,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.002,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )
            task_accel.timing.cfg_samp_clk_timing(
                self.sr, sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self.chunk
            )
            # 电压
            task_voltage.ai_channels.add_ai_voltage_chan(
                self.voltage_ch,
                min_val=self.voltage_range[0], max_val=self.voltage_range[1]
            )
            task_voltage.timing.cfg_samp_clk_timing(
                self.sr, sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self.chunk
            )

            reader_accel = AnalogMultiChannelReader(task_accel.in_stream)
            reader_voltage = AnalogMultiChannelReader(task_voltage.in_stream)

            buf_accel = np.zeros((self.num_accel, self.chunk), dtype=np.float64)
            buf_voltage = np.zeros((self.num_voltage, self.chunk), dtype=np.float64)

            task_accel.start()
            task_voltage.start()

            while self.is_running and self.sample_count < self.max_samples:
                try:
                    reader_accel.read_many_sample(buf_accel, self.chunk, timeout=0.5)
                    reader_voltage.read_many_sample(buf_voltage, self.chunk, timeout=0.5)
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
                    # 合并数据
                    data_chunk = np.vstack([buf_accel[:, :actual], buf_voltage[:, :actual]])
                    # 保存到full
                    self.full_data[0:self.num_accel, start:end] = buf_accel[:, :actual]
                    self.full_data[self.num_accel:, start:end] = buf_voltage[:, :actual]
                    self.sample_count = end
                    self.full_t[start:end] = t_chunk
                    if self.data_callback:
                        self.data_callback(t_chunk, data_chunk)
                    break
                else:
                    t_chunk = np.linspace(start/self.sr, end/self.sr, self.chunk, endpoint=False)
                    data_chunk = np.vstack([buf_accel, buf_voltage])
                    self.full_data[0:self.num_accel, start:end] = buf_accel
                    self.full_data[self.num_accel:, start:end] = buf_voltage
                    self.sample_count = end
                    self.full_t[start:end] = t_chunk
                    if self.data_callback:
                        self.data_callback(t_chunk, data_chunk)

        except Exception as e:
            print(f"[采集] 错误: {e}")
        finally:
            task_accel.close()
            task_voltage.close()