import asyncio
import json
import os
from collections import deque
import websockets
from config import WS_PORT, MODEL_DIR

left_data = deque(maxlen=1)
right_data = deque(maxlen=1)

station_info = {
    "left": {"barcode": "", "spec": "", "mode": ""},
    "right": {"barcode": "", "spec": "", "mode": ""}
}

connected_clients = set()
ws_loop = None
pending_label = {"left": None, "right": None}

# ---------- 新增：数据入队使能 ----------
data_enabled = {"left": True, "right": True}   # 默认启用，按需调整

def enable_data(side, enabled):
    """启用/禁用指定工位的数据入队，禁用时会清空已有数据"""
    data_enabled[side] = enabled
    if not enabled:
        clear_data(side)

def clear_data(side):
    """清空指定工位的缓存数据"""
    if side == "left":
        left_data.clear()
    else:
        right_data.clear()

# ---------- 原有函数（修改 put_data） ----------
def get_model_list():
    if not os.path.exists(MODEL_DIR):
        return []
    return [f[:-4] for f in os.listdir(MODEL_DIR) if f.endswith('.pth')]

def start_ws_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    global ws_loop
    ws_loop = loop
    loop.run_until_complete(ws_main())

async def ws_main():
    async with websockets.serve(handler, "0.0.0.0", WS_PORT):
        print(f"[WebSocket] 服务启动 ws://localhost:{WS_PORT}")
        asyncio.create_task(data_broadcast_loop())
        await asyncio.Future()

async def handler(websocket, path):
    connected_clients.add(websocket)
    try:
        await websocket.send(json.dumps({
            "type": "model_list",
            "models": get_model_list()
        }))
        for side in ["left", "right"]:
            info = station_info[side]
            await websocket.send(json.dumps({
                "type": "info",
                "side": side,
                "barcode": info["barcode"],
                "spec": info["spec"],
                "mode": info["mode"]
            }))
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                if msg_type == "select_model":
                    print(f"[WS] 选择模型: {data.get('model_id')}")
                    await websocket.send(json.dumps({
                        "type": "model_selected",
                        "model": data.get('model_id')
                    }))
                elif msg_type == "label":
                    side = data.get("side")
                    label = data.get("label")
                    if side in pending_label:
                        pending_label[side] = label
                        print(f"[WS] 人工标注 {side} -> {label}")
                elif msg_type in ("start", "stop"):
                    print(f"[WS] 收到 {msg_type} 指令")
                else:
                    print(f"[WS] 未知消息: {msg_type}")
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)

async def data_broadcast_loop():
    while True:
        broadcast_data_batch()
        await asyncio.sleep(0.05)

def broadcast_data_batch():
    if not connected_clients:
        return
    left_block = left_data[-1] if left_data else None
    right_block = right_data[-1] if right_data else None
    if left_block is None and right_block is None:
        return
    time_vals = left_block["time"] if left_block else right_block["time"]
    msg = {
        "type": "data_batch",
        "time": time_vals,
        "left_x": left_block["x"] if left_block else [],
        "left_y": left_block["y"] if left_block else [],
        "left_z": left_block["z"] if left_block else [],
        "left_current": left_block["current"] if left_block else [],
        "right_x": right_block["x"] if right_block else [],
        "right_y": right_block["y"] if right_block else [],
        "right_z": right_block["z"] if right_block else [],
        "right_current": right_block["current"] if right_block else []
    }
    json_msg = json.dumps(msg)
    for ws in list(connected_clients):
        asyncio.run_coroutine_threadsafe(ws.send(json_msg), ws_loop)

def update_station_info(side, barcode, spec, mode):
    station_info[side] = {"barcode": barcode, "spec": spec, "mode": mode}
    msg = json.dumps({
        "type": "info",
        "side": side,
        "barcode": barcode,
        "spec": spec,
        "mode": mode
    })
    for ws in list(connected_clients):
        asyncio.run_coroutine_threadsafe(ws.send(msg), ws_loop)

def send_result(side, result, score, message):
    msg = json.dumps({
        "type": "result",
        "side": side,
        "result": result,
        "score": score,
        "message": message
    })
    for ws in list(connected_clients):
        asyncio.run_coroutine_threadsafe(ws.send(msg), ws_loop)

def put_data(side, time_array, data_2d):
    # 检查该工位是否允许数据入队
    if not data_enabled.get(side, True):
        return
    time_list = time_array.tolist()
    n = len(time_list)
    d = {
        "time": time_list,
        "x": data_2d[0].tolist() if data_2d.shape[0] > 0 else [0.0]*n,
        "y": data_2d[1].tolist() if data_2d.shape[0] > 1 else [0.0]*n,
        "z": data_2d[2].tolist() if data_2d.shape[0] > 2 else [0.0]*n,
        "current": data_2d[4].tolist() if data_2d.shape[0] > 4 else [0.0]*n
    }
    if side == "left":
        left_data.append(d)
    else:
        right_data.append(d)

def get_pending_label(side):
    val = pending_label.get(side)
    pending_label[side] = None
    return val