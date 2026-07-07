"""
模拟后端：先发右侧数据，3 秒后再发左侧数据（复现左右时间串扰 bug）
"""

import asyncio
import json
import math
import random
import websockets


async def handler(websocket):
    print(f"[连接] 前端已连接: {websocket.remote_address}")
    try:
        # 发送模型列表 + info
        await websocket.send(json.dumps({
            "type": "model_list", "models": ["model_A", "model_B"]}))
        await websocket.send(json.dumps({
            "type": "info", "side": "right",
            "barcode": "TEST_RIGHT_001", "spec": "规格A", "mode": "auto"}))
        await websocket.send(json.dumps({
            "type": "info", "side": "left",
            "barcode": "TEST_LEFT_001", "spec": "规格B", "mode": "auto"}))

        await asyncio.sleep(2)

        # ===== Phase 1: 只有右侧 (0~3 秒) =====
        print("[Phase1] 仅右侧采集 (0~3s)")
        t_start = 0.0
        t_right = 0.0
        t_left = 0.0
        dt = 1.0 / 4800
        batch_size = 480  # ~0.1s per batch
        phase1_duration = 3.0

        while t_right < phase1_duration:
            times_r = [t_right + i * dt for i in range(batch_size)]
            vals_r = [math.sin(2 * math.pi * 80 * tt) * 0.5 + random.gauss(0, 0.1) for tt in times_r]
            zeros = []
            # 左侧没有数据
            await websocket.send(json.dumps({
                "type": "data_batch",
                "time": times_r,
                "left_x": zeros, "left_y": zeros, "left_z": zeros, "left_current": zeros,
                "right_x": vals_r, "right_y": vals_r, "right_z": vals_r,
                "right_current": [1.5 + 0.1 * random.gauss(0, 1) for _ in vals_r],
            }))
            t_right += batch_size * dt
            await asyncio.sleep(0.1)

        # ===== Phase 2: 左右同时采集 (3~8 秒) =====
        print("[Phase2] 左右同时采集 (3~8s)")
        t_left = 0.0
        phase2_duration = 5.0

        while t_left < phase2_duration:
            times_left = [t_left + i * dt for i in range(batch_size)]
            times_right = [t_right + i * dt for i in range(batch_size)]
            vals_l = [math.sin(2 * math.pi * 50 * tt) * 0.6 + random.gauss(0, 0.1) for tt in times_left]
            vals_r = [math.sin(2 * math.pi * 80 * tt) * 0.5 + random.gauss(0, 0.1) for tt in times_right]
            # 模拟后端：time 用左侧的（优先）
            await websocket.send(json.dumps({
                "type": "data_batch",
                "time": times_left,   # ← 关键：用左侧时间，右侧数据也被绑上左侧时间
                "left_x": vals_l, "left_y": vals_l, "left_z": vals_l,
                "left_current": [1.8 + 0.1 * random.gauss(0, 1) for _ in vals_l],
                "right_x": vals_r, "right_y": vals_r, "right_z": vals_r,
                "right_current": [1.5 + 0.1 * random.gauss(0, 1) for _ in vals_r],
            }))
            t_left += batch_size * dt
            t_right += batch_size * dt
            await asyncio.sleep(0.1)

        # 发送结果
        await websocket.send(json.dumps({
            "type": "result", "side": "right",
            "result": "OK", "score": 0.95, "message": "右侧合格"}))
        await websocket.send(json.dumps({
            "type": "result", "side": "left",
            "result": "NG", "score": 0.30, "message": "左侧不合格"}))

        print("[完成]")
        await asyncio.sleep(60)

    except websockets.exceptions.ConnectionClosed:
        pass


async def main():
    async with websockets.serve(handler, "0.0.0.0", 8081):
        print("=" * 55)
        print("[Mock Staggered] ws://localhost:8081")
        print("Phase1: 仅右侧 3 秒 → Phase2: 左右同时 5 秒")
        print("=" * 55)
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[退出]")
