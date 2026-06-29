import time
import threading
from config import *
from station_worker import StationWorker
from plc_manager import plc_manager
from heartbeat import Heartbeat
import websocket_server
from shared_data_acquisition import shared_daq  # 导入共享采集


def start_ws():
    websocket_server.start_ws_server()


def main():
    # 启动WebSocket
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()
    time.sleep(1)

    # 启动心跳
    # heartbeat = Heartbeat()
    # heartbeat.start()

    # 检查PLC连接
    try:
        mode = plc_manager.read_mode()
        print(f"[主程序] PLC连接正常，当前模式: {'自动' if mode == 1 else '人工'}")
    except Exception as e:
        print(f"[主程序] PLC连接异常: {e}")

    # 启动共享采集（但不开始采集，等待工位START命令）
    # shared_daq.start()  # 可以在工位收到START时启动

    # 创建工位线程
    left_worker = StationWorker("left")
    right_worker = StationWorker("right")

    print("[主程序] 双工位已启动，使用共享NI采集")
    print("[主程序] 按 Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[主程序] 收到中断，正在关闭...")
    finally:
        left_worker.stop()
        right_worker.stop()
        # heartbeat.stop()
        shared_daq.stop()  # 停止共享采集
        plc_manager.close()
        print("[主程序] 已退出")


if __name__ == "__main__":
    main()