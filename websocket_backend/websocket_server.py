import asyncio
import json
from collections import deque
import websockets

# 全局数据队列（每个工位只保留最新一块）
left_data = deque(maxlen=1)
right_data = deque(maxlen=1)

station_info = {"left": {"barcode": "", "spec": "", "mode": ""},
                "right": {"barcode": "", "spec": "", "mode": ""}}

connected_clients = set()
ws_loop = None
pending_label = {"left": None, "right": None}

def start_ws_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    global ws_loop
    ws_loop = loop
    loop.run_until_complete(ws_main())

async def ws_main():
    async with websockets.serve(handler, "0.0.0.0", 8080):
        print("[WebSocket] 服务启动 ws://localhost:8080")
        asyncio.create_task(data_broadcast_loop())
        await asyncio.Future()

async def handler(websocket, path):
    connected_clients.add(websocket)
    try:
        # 发送模型列表
        await websocket.send(json.dumps({"type": "model_list", "models": ["model_A", "model_B"]}))
        # 发送当前状态
        for side in ["left", "right"]:
            info = station_info[side]
            await websocket.send(json.dumps({"type": "info", "side": side, "barcode": info["barcode"],
                                             "spec": info["spec"], "mode": info["mode"]}))
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                if msg_type == "select_model":
                    print(f"[WS] 选择模型: {data.get('model_id')}")
                    await websocket.send(json.dumps({"type": "model_selected", "model": data.get('model_id')}))
                elif msg_type == "label":
                    side = data.get("side")
                    label = data.get("label")
                    print(f"[WS] 人工标注 {side} -> {label}")
                    pending_label[side] = label
                elif msg_type in ("start", "stop"):
                    print(f"[WS] 收到{msg_type}指令")
                else:
                    print(f"[WS] 未知消息: {msg_type}")
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)

def broadcast_data_batch():
    if not connected_clients:
        return
    left_block = left_data[-1] if left_data else None
    right_block = right_data[-1] if right_data else None
    if left_block is None and right_block is None:
        return
    time_vals = left_block["time"] if left_block else right_block["time"]
    msg = {"type": "data_batch", "time": time_vals,
           "left_x": left_block["x"] if left_block else [],
           "left_y": left_block["y"] if left_block else [],
           "left_z": left_block["z"] if left_block else [],
           "left_current": left_block["current"] if left_block else [],
           "right_x": right_block["x"] if right_block else [],
           "right_y": right_block["y"] if right_block else [],
           "right_z": right_block["z"] if right_block else [],
           "right_current": right_block["current"] if right_block else []}
    json_msg = json.dumps(msg)
    for ws in list(connected_clients):
        asyncio.run_coroutine_threadsafe(ws.send(json_msg), ws_loop)

async def data_broadcast_loop():
    while True:
        broadcast_data_batch()
        await asyncio.sleep(0.05)

# 对外接口
def update_station_info(side, barcode, spec, mode):
    station_info[side].update({"barcode": barcode, "spec": spec, "mode": mode})
    msg = json.dumps({"type": "info", "side": side, "barcode": barcode, "spec": spec, "mode": mode})
    for ws in list(connected_clients):
        asyncio.run_coroutine_threadsafe(ws.send(msg), ws_loop)

def send_result(side, result, score, message):
    msg = json.dumps({"type": "result", "side": side, "result": result, "score": score, "message": message})
    for ws in list(connected_clients):
        asyncio.run_coroutine_threadsafe(ws.send(msg), ws_loop)

def put_data(side, time_array, data_2d):
    """data_2d: (channels, samples)，映射为x,z,current, y填充0"""
    time_list = time_array.tolist()
    d = {"time": time_list,
         "x": data_2d[0].tolist() if data_2d.shape[0] > 0 else [],
         "y": [0.0] * len(time_list),
         "z": data_2d[1].tolist() if data_2d.shape[0] > 1 else [],
         "current": data_2d[2].tolist() if data_2d.shape[0] > 2 else []}
    if side == "left":
        left_data.append(d)
    else:
        right_data.append(d)

def get_pending_label(side):
    val = pending_label[side]
    pending_label[side] = None
    return val