import time
import os
import threading
from config import *
from station_worker import StationWorker
from plc_comm import PLCClient
from heartbeat import Heartbeat
import websocket_server

# ==================== 测试配置 ====================
TEST_MODE = "simulate"  # "simulate" 或 "real"
# TEST_MODE = "real"

# 模拟PLC步骤（模拟模式使用）
SIMULATED_STEPS = [
    (STEP_READY, 2),
    (STEP_TEST_START, 5),  # 采集5秒
    (STEP_TEST_END, 3),
]


# =================================================

def start_ws():
    """启动WebSocket服务"""
    websocket_server.start_ws_server()


def simulate_plc_worker(worker_name, steps):
    """
    模拟PLC发送步骤的线程
    """
    print(f"[模拟PLC] {worker_name} 线程启动")
    try:
        plc = PLCClient(PLC_IP, PLC_PORT)
        plc.connect()

        for step, delay in steps:
            print(f"\n[模拟PLC] {worker_name} -> STEP {step}")
            # 写入PLC_STEP寄存器（使用工位对应的寄存器）
            reg = STATIONS[worker_name]["plc_step_reg"]
            plc.write_word(reg, step)

            # 等待PC响应（简单等待）
            time.sleep(1)

            # 检查PC STEP确认
            pc_step = plc.read_word(STATIONS[worker_name]["pc_step_reg"])
            print(f"[模拟PLC] {worker_name} PC响应 STEP = {pc_step}")

            # 剩余延迟
            remaining = delay - 1
            if remaining > 0:
                time.sleep(remaining)

        plc.close()
        print(f"[模拟PLC] {worker_name} 测试步骤完成")

    except Exception as e:
        print(f"[模拟PLC] {worker_name} 异常: {e}")


def test_without_hardware():
    """
    纯软件模拟测试（不需要任何硬件）
    """
    print("\n" + "=" * 60)
    print("纯软件模拟测试模式（无硬件）")
    print("=" * 60 + "\n")

    # 使用模拟数据创建临时工位
    from unittest.mock import MagicMock

    # 创建模拟的PLC和DAQ
    original_plc = PLCClient
    original_daq = None  # 用于替换

    # 修改StationWorker使用模拟数据
    class MockStationWorker(StationWorker):
        def __init__(self, name):
            self.name = name
            self.model = None
            self.station_cfg = STATIONS[name]
            # 使用模拟PLC
            self.plc = MagicMock()
            self.plc.read_mode.return_value = 1
            self.plc.read_station_step.return_value = STEP_READY
            self.plc.read_barcode.return_value = "MOCK_BARCODE_001"
            self.plc.read_product_spec.return_value = "MOCK_SPEC"
            self.plc.read_manual_result.return_value = 1

            # 使用模拟DAQ
            self.daq = MagicMock()
            self.daq.start = lambda: None
            self.daq.stop = lambda: (None, None)

            self.state = "idle"
            self.running = True
            self.current_barcode = ""
            self.current_spec = ""
            self.last_heartbeat = time.time()
            self.thread = threading.Thread(target=self.run_mock, daemon=True)
            self.thread.start()

        def run_mock(self):
            """模拟运行，不连接硬件"""
            print(f"[{self.name}] 模拟线程启动")
            # 直接模拟完整流程
            time.sleep(1)

            # 模拟READY
            self.current_barcode = "MOCK_BARCODE_001"
            self.current_spec = "MOCK_SPEC"
            print(f"[{self.name}] 条码:MOCK_BARCODE_001 规格:MOCK_SPEC")

            # 模拟采集
            print(f"[{self.name}] 开始采集（模拟）")
            time.sleep(2)

            # 模拟结束
            print(f"[{self.name}] 结束采集，处理...")

            # 模拟数据
            import numpy as np
            t = np.linspace(0, 1, 1000)
            data = np.random.randn(5, 1000)

            # 模拟推理
            label = 0  # OK
            print(f"[{self.name}] 自动判定: OK")

            # 模拟保存
            self.save_per_channel(t, data, label)
            print(f"[{self.name}] 处理完成\n")

        def stop(self):
            self.running = False
            if self.thread:
                self.thread.join(timeout=2.0)
            print(f"[{self.name}] 模拟线程停止")

    # 启动模拟工位
    left_worker = MockStationWorker("left")
    right_worker = MockStationWorker("right")

    print("[主程序] 模拟工位已启动")

    try:
        # 等待模拟完成
        time.sleep(10)
        print("\n✅ 纯软件模拟测试完成!")
        print("请检查 logs/saved_data/ 目录是否有模拟数据")

    except KeyboardInterrupt:
        print("中断")
    finally:
        left_worker.stop()
        right_worker.stop()


def test_with_hardware_simulated_plc():
    """
    真实硬件 + 模拟PLC步骤测试
    """
    print("\n" + "=" * 60)
    print("真实硬件测试模式（PLC步骤由软件模拟）")
    print("=" * 60 + "\n")
    print("⚠️ 警告: 此模式需要真实的NI设备连接")
    print("⚠️ PLC步骤由软件模拟发送")
    print("\n按 Enter 继续，或 Ctrl+C 取消...")
    input()

    # 启动WebSocket
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()
    time.sleep(1)

    # 启动心跳
    heartbeat = Heartbeat()
    heartbeat.start()

    # 判断模式
    plc_temp = PLCClient(PLC_IP, PLC_PORT)
    try:
        plc_temp.connect()
        mode = plc_temp.read_mode()
        plc_temp.close()
        print(f"[主程序] 当前模式: {'自动' if mode == 1 else '人工'}")
    except:
        print("[主程序] 警告: PLC连接失败，使用默认模式")
        mode = 1

    # 创建工位线程
    left_worker = StationWorker("left")
    right_worker = StationWorker("right")

    print("[主程序] 双工位已启动")

    # 启动模拟PLC线程
    left_plc_thread = threading.Thread(
        target=simulate_plc_worker,
        args=("left", SIMULATED_STEPS),
        daemon=True
    )
    right_plc_thread = threading.Thread(
        target=simulate_plc_worker,
        args=("right", SIMULATED_STEPS),
        daemon=True
    )
    left_plc_thread.start()
    right_plc_thread.start()

    print("[主程序] 等待测试完成...")

    try:
        # 等待模拟完成（稍大于总时间）
        total_time = sum(delay for _, delay in SIMULATED_STEPS) + 5
        time.sleep(total_time)
        print("\n✅ 硬件测试完成!")

    except KeyboardInterrupt:
        print("中断")
    finally:
        left_worker.stop()
        right_worker.stop()
        heartbeat.stop()
        print("[主程序] 已退出")


def test_real_full():
    """
    真实硬件 + 真实PLC（需要PLC实际发送步骤）
    """
    print("\n" + "=" * 60)
    print("真实完整测试模式（需要真实PLC和NI设备）")
    print("=" * 60 + "\n")
    print("⚠️ 警告: 此模式需要:")
    print("  1. PLC连接正常 (IP: {})".format(PLC_IP))
    print("  2. NI设备已连接")
    print("  3. PLC正在发送步骤指令")
    print("\n按 Enter 继续，或 Ctrl+C 取消...")
    input()

    # 启动WebSocket
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()
    time.sleep(1)

    # 启动心跳
    heartbeat = Heartbeat()
    heartbeat.start()

    # 判断模式
    plc_temp = PLCClient(PLC_IP, PLC_PORT)
    try:
        plc_temp.connect()
        mode = plc_temp.read_mode()
        plc_temp.close()
        print(f"[主程序] 当前模式: {'自动' if mode == 1 else '人工'}")
    except Exception as e:
        print(f"[主程序] PLC连接失败: {e}")
        return

    # 创建工位线程
    left_worker = StationWorker("left")
    right_worker = StationWorker("right")

    print("[主程序] 双工位已启动")
    print("[主程序] 等待PLC发送指令...")
    print("[主程序] 按 Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[主程序] 收到中断，正在关闭...")
    finally:
        left_worker.stop()
        right_worker.stop()
        heartbeat.stop()
        print("[主程序] 已退出")


def main():
    """主测试入口"""
    print("\n" + "=" * 60)
    print("流程测试工具")
    print("=" * 60)
    print("\n选择测试模式:")
    print("  1. 纯软件模拟测试 (无需任何硬件)")
    print("  2. 真实硬件 + 模拟PLC步骤 (需要NI设备)")
    print("  3. 真实完整测试 (需要PLC + NI设备)")
    print("  4. 退出")

    choice = input("\n请输入选项 (1-4): ").strip()

    if choice == "1":
        test_without_hardware()
    elif choice == "2":
        test_with_hardware_simulated_plc()
    elif choice == "3":
        test_real_full()
    else:
        print("退出")


if __name__ == "__main__":
    main()