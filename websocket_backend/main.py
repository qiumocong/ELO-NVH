import time
from config import *
from station_worker import StationWorker
from model_inference import load_model
from plc_comm import PLCClient
from heartbeat import Heartbeat
import threading
import websocket_server

def start_ws():
    websocket_server.start_ws_server()

def main():
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()
    # 启动心跳
    heartbeat = Heartbeat()
    heartbeat.start()

    # 判断模式
    plc_temp = PLCClient(PLC_IP, PLC_PORT)
    plc_temp.connect()
    mode = plc_temp.read_mode()
    plc_temp.close()
    model = None
    if mode == 1:
        model = load_model()
        print("[主程序] 自动模式，模型已加载")
    else:
        print("[主程序] 人工模式")

    # 创建左右工位工作线程
    left_worker = StationWorker("left", model)
    right_worker = StationWorker("right", model)

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