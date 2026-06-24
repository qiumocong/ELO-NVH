"""
模拟 WebSocket 后端 — 用于前后端联调测试

行为完全模拟 websocket_backend：
1. 前端连接后 → 发送 model_list + 左右工位 info
2. 2 秒后持续推送 data_batch（左右两组 x/y/z/current）
3. 8 秒后发送检测结果

启动：
    python mock_ws_server.py

然后前端用：
    python main.py --ws
"""

import asyncio
import json
import math
import random
import time
import websockets

connected_clients = set()


async def handler(websocket):
    connected_clients.add(websocket)
    print("[连接] 前端已连接")
    try:
        # 1. 发送模型列表
        await websocket.send(json.dumps({
            "type": "model_list",
            "models": ["model_A", "model_B"],
        }))

        # 2. 发送左右工位信息
        await websocket.send(json.dumps({
            "type": "info", "side": "left",
            "barcode": "OBJ_TEST_001_L",
            "spec": "规格A",
            "mode": "auto",
        }))
        await websocket.send(json.dumps({
            "type": "info", "side": "right",
            "barcode": "OBJ_TEST_001_R",
            "spec": "规格B",
            "mode": "manual",
        }))

        # 3. 等待 2 秒，模拟 PLC 触发
        await asyncio.sleep(2)

        # 4. 持续推送数据 8 秒
        t = 0.0
        dt = 0.001
        batch_size = 50
        start = time.time()
        while time.time() - start < 8:
            times = []
            lx, ly, lz, lc = [], [], [], []
            rx, ry, rz, rc = [], [], [], []

            for _ in range(batch_size):
                times.append(round(t, 6))

                # 左：chirp 10→100Hz
                f0, f1, t1 = 10, 100, 1.0
                p_l = 2 * math.pi * (f0 * t + (f1 - f0) * t ** 3 / (3 * t1 ** 2))
                lx.append(math.sin(p_l) * 0.8 + random.gauss(0, 0.1))
                ly.append(math.sin(2 * math.pi * 120 * t) * 0.5 + random.gauss(0, 0.15))
                lz.append(math.sin(2 * math.pi * 80 * t) * 0.6 + random.gauss(0, 0.18))
                lc.append(1.5 + 0.3 * math.sin(2 * math.pi * 5 * t) + random.gauss(0, 0.05))

                # 右：chirp 30→150Hz
                f0r, f1r = 30, 150
                p_r = 2 * math.pi * (f0r * t + (f1r - f0r) * t ** 3 / (3 * t1 ** 2))
                rx.append(math.sin(p_r) * 0.7 + random.gauss(0, 0.1))
                ry.append(math.sin(2 * math.pi * 90 * t) * 0.55 + random.gauss(0, 0.12))
                rz.append(math.sin(2 * math.pi * 60 * t) * 0.65 + random.gauss(0, 0.16))
                rc.append(1.8 + 0.25 * math.sin(2 * math.pi * 6 * t) + random.gauss(0, 0.04))

                t += dt

            await websocket.send(json.dumps({
                "type": "data_batch",
                "time": times,
                "left_x": lx, "left_y": ly, "left_z": lz, "left_current": lc,
                "right_x": rx, "right_y": ry, "right_z": rz, "right_current": rc,
            }))
            await asyncio.sleep(0.05)

        # 5. 发送检测结果
        await websocket.send(json.dumps({
            "type": "result", "side": "left",
            "result": "OK", "score": 0.96, "message": "左侧检测合格",
        }))
        await websocket.send(json.dumps({
            "type": "result", "side": "right",
            "result": "NG", "score": 0.32, "message": "右侧检测不合格",
        }))

        print("[完成] 一轮检测结束")
        await asyncio.sleep(60)  # 保持连接

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)
        print("[断开] 前端已断开")


async def main():
    async with websockets.serve(handler, "localhost", 8080):
        print("=" * 50)
        print("[Mock WS Server] 模拟后端已启动 ws://localhost:8080")
        print("请在另一个终端运行: python main.py --ws")
        print("=" * 50)
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[退出]")
