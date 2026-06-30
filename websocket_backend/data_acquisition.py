import nidaqmx
import numpy as np
import time
from nidaqmx.constants import AcquisitionType, AccelSensitivityUnits, AccelUnits, ExcitationSource
from nidaqmx.constants import TerminalConfiguration, VoltageUnits
from nidaqmx.stream_readers import AnalogMultiChannelReader
import threading
from config import SAMPLE_RATE, CHUNK_SAMPLES, MAX_COLLECT_TIME
from config import RANGE_9234, SENSITIVITY, SENSOR_OUTPUT_MAX
from config import VOLTAGE_SENSOR_MAX, CURRENT_SENSOR_MAX

class DataAcquisition:
    def __init__(self, accel_channels, voltage_channel, current_channel,
                 data_callback=None):
        """
        独立采集类，每个工位实例化一个
        accel_channels: 加速度通道，如 "cDAQ1Mod1/ai0:2"
        voltage_channel: 电压通道，如 "cDAQ1Mod3/ai2"
        current_channel: 电流通道，如 "cDAQ1Mod3/ai3"
        data_callback: 每块数据回调 callback(t_chunk, data_chunk)
                       data_chunk shape: (5, samples) [x,y,z,voltage,current]
        """
        self.accel_ch = accel_channels
        self.voltage_ch = voltage_channel
        self.current_ch = current_channel

        self.sr = SAMPLE_RATE
        self.chunk = CHUNK_SAMPLES
        self.max_samples = int(self.sr * MAX_COLLECT_TIME)

        self.accel_range = RANGE_9234
        self.sensitivity = SENSITIVITY
        self.sensor_output_max = SENSOR_OUTPUT_MAX
        self.voltage_sensor_max = VOLTAGE_SENSOR_MAX
        self.current_sensor_max = CURRENT_SENSOR_MAX

        self.is_running = False
        self._stop_requested = False
        self.thread = None
        self.data_callback = data_callback

        self.full_t = None
        self.full_data = None
        self.sample_count = 0
        self.has_data = False

        # 解析加速度通道数量
        if ':' in accel_channels:
            start, end = accel_channels.split(':')
            start_num = int(''.join(filter(str.isdigit, start.split('/')[-1])))
            end_num = int(''.join(filter(str.isdigit, end)))
            self.num_accel = end_num - start_num + 1
        else:
            self.num_accel = 1

    def start(self, reset_time=True):
        if self.is_running:
            return
        if reset_time:
            self.sample_count = 0
            self.has_data = False
            self.full_t = np.empty(self.max_samples, dtype=np.float64)
            self.full_data = np.empty((5, self.max_samples), dtype=np.float64)
        self.is_running = True
        self._stop_requested = False
        self.thread = threading.Thread(target=self._acq_loop, daemon=True)
        self.thread.start()
        print(f"[采集] 采集已启动 (通道: {self.accel_ch}, {self.voltage_ch}, {self.current_ch})")

    def stop(self):
        print("[采集] 收到停止请求...")
        self._stop_requested = True
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print(f"[采集] 采集已停止, 共采集 {self.sample_count} 个样本")

    def get_data(self):
        if self.full_data is None or self.sample_count == 0 or not self.has_data:
            return np.array([]), np.empty((5, 0))
        return self.full_t[:self.sample_count], self.full_data[:, :self.sample_count]

    def _convert_data(self, data_block):
        """
        data_block: (samples, 5) 顺序 [accel_x, accel_y, accel_z, raw_voltage, raw_current]
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

            # 加速度通道（可能为 "ai0:2"，自动识别通道数）
            task.ai_channels.add_ai_accel_chan(
                self.accel_ch,
                min_val=self.accel_range[0], max_val=self.accel_range[1],
                sensitivity=self.sensitivity,
                sensitivity_units=AccelSensitivityUnits.MILLIVOLTS_PER_G,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=0.004,
                units=AccelUnits.METERS_PER_SECOND_SQUARED
            )

            # 电压通道
            task.ai_channels.add_ai_voltage_chan(
                self.voltage_ch, min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS, terminal_config=TerminalConfiguration.DIFF
            )

            # 电流通道
            task.ai_channels.add_ai_voltage_chan(
                self.current_ch, min_val=0.0, max_val=self.sensor_output_max,
                units=VoltageUnits.VOLTS, terminal_config=TerminalConfiguration.DIFF
            )

            task.timing.cfg_samp_clk_timing(
                self.sr, sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self.chunk * 2
            )
            task.in_stream.input_buf_size = 1000000

            reader = AnalogMultiChannelReader(task.in_stream)
            # buffer: (加速度通道数 + 2, chunk)
            total_ch = self.num_accel + 2
            buffer_all = np.zeros((total_ch, self.chunk), dtype=np.float64)

            task.start()
            print(f"[采集] NI任务已启动，{total_ch}通道")

            while self.is_running and self.sample_count < self.max_samples:
                if self._stop_requested:
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
                        print(f"[采集] 读取错误: {e}")
                        break

                start = self.sample_count
                end = start + self.chunk
                if end > self.max_samples:
                    end = self.max_samples
                    actual = end - start
                    if actual <= 0:
                        break
                    t_chunk = np.linspace(start / self.sr, end / self.sr, actual, endpoint=False)
                    # 数据块形状: (actual, total_ch)
                    data_block = buffer_all[:, :actual].T
                    # 转换为 [x, y, z, voltage, current]
                    # 假设加速度通道按顺序为 x,y,z，如果只有2通道则y补零
                    accel_data = data_block[:, :self.num_accel]
                    if self.num_accel < 3:
                        # 补零
                        pad = np.zeros((actual, 3 - self.num_accel))
                        accel_data = np.hstack((accel_data, pad))
                    else:
                        accel_data = accel_data[:, :3]  # 只取前3
                    # 电压和电流
                    raw_voltage = data_block[:, self.num_accel]
                    raw_current = data_block[:, self.num_accel + 1]
                    # 组装 (actual, 5)
                    combined = np.column_stack((accel_data, raw_voltage, raw_current))
                    converted = self._convert_data(combined)

                    self.full_data[:, start:end] = converted
                    self.full_t[start:end] = t_chunk
                    self.sample_count = end
                    self.has_data = True

                    if self.data_callback:
                        self.data_callback(t_chunk, converted)

                    break
                else:
                    t_chunk = np.linspace(start / self.sr, end / self.sr, self.chunk, endpoint=False)
                    data_block = buffer_all[:, :].T
                    accel_data = data_block[:, :self.num_accel]
                    if self.num_accel < 3:
                        pad = np.zeros((self.chunk, 3 - self.num_accel))
                        accel_data = np.hstack((accel_data, pad))
                    else:
                        accel_data = accel_data[:, :3]
                    raw_voltage = data_block[:, self.num_accel]
                    raw_current = data_block[:, self.num_accel + 1]
                    combined = np.column_stack((accel_data, raw_voltage, raw_current))
                    converted = self._convert_data(combined)

                    self.full_data[:, start:end] = converted
                    self.full_t[start:end] = t_chunk
                    self.sample_count = end
                    self.has_data = True

                    if self.data_callback:
                        self.data_callback(t_chunk, converted)

                time.sleep(0.002)

        except Exception as e:
            print(f"[采集] 错误: {e}")
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
            print("[采集] NI任务已关闭")