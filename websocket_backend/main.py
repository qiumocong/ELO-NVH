import time
from config import *
from station_worker import StationWorker
from plc_comm import PLCClient
from heartbeat import Heartbeat
import threading
import websocket_server

def start_ws():
    websocket_server.start_ws_server()

def main():
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()
    # 启动心跳（用于保持PLC连接）
    heartbeat = Heartbeat()
    heartbeat.start()

    # 仅判断模式，不预加载模型
    plc_temp = PLCClient(PLC_IP, PLC_PORT)
    plc_temp.connect()
    mode = plc_temp.read_mode()
    plc_temp.close()
    print(f"[主程序] 当前模式: {'自动' if mode == 1 else '人工'}")

    # 创建工位线程，不传入模型
    left_worker = StationWorker("left")
    right_worker = StationWorker("right")

    print("[主程序] 双工位已启动，按 Ctrl+C 退出")
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

if __name__ == "__main__":
    main()