import time
import threading
from config import *
from station_worker import StationWorker
from plc_manager import plc_manager
import websocket_server
from shared_data_acquisition import shared_daq

def start_ws():
    websocket_server.start_ws_server()

def main():
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()
    time.sleep(1)

    try:
        mode = plc_manager.read_mode()
        print(f"[主程序] PLC连接正常，当前模式: {'自动' if mode == 1 else '人工'}")
    except Exception as e:
        print(f"[主程序] PLC连接异常: {e}")

    left_worker = StationWorker("left")
    right_worker = StationWorker("right")

    print("[主程序] 双工位已启动，共享NI采集")
    print("[主程序] 按 Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[主程序] 收到中断，正在关闭...")
    finally:
        left_worker.stop()
        right_worker.stop()
        shared_daq.stop()
        plc_manager.close()
        print("[主程序] 已退出")

if __name__ == "__main__":
    main()