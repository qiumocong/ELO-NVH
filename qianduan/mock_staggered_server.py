"""
模拟后端：Phase1 仅右侧 3s → Phase2 左右同时 5s
每批 480 点 @4800Hz ≈ 0.1s，每批间隔 0.1s (模拟 NI 采集)
"""
import asyncio
import json
import math
import random
import websockets

async def handler(websocket):
    print(f"[连接] 前端已连接: {websocket.remote_address}")
    try:
        await websocket.send(json.dumps({
            "type": "model_list", "models": ["model_A", "model_B"]}))
        await websocket.send(json.dumps({
            "type": "info", "side": "right",
            "barcode": "TEST_RIGHT_001", "spec": "规格A", "mode": "auto"}))
        await websocket.send(json.dumps({
            "type": "info", "side": "left",
            "barcode": "TEST_LEFT_001", "spec": "规格B", "mode": "auto"}))

        await asyncio.sleep(2)

        lbid = 0     # 左侧批次计数 (模拟后端 left_batch_id)
        rbid = 0     # 右侧批次计数
        bseq = 0     # 广播序号

        dt = 1.0 / 4800
        batch_size = 480
        t_right = 0.0

        # Phase 1: 仅右侧 3s (30 个批次)
        print("[Phase1] 仅右侧采集 30 批 (~3s)")
        for _ in range(30):
            rbid += 1
            t0 = t_right
            times_r = [t0 + i * dt for i in range(batch_size)]
            vals_r = [math.sin(2 * math.pi * 80 * tt) * 0.5 + random.gauss(0, 0.1) for tt in times_r]
            zeros = []
            await websocket.send(json.dumps({
                "type": "data_batch",
                "time": times_r,
                "left_x": zeros, "left_y": zeros, "left_z": zeros, "left_current": zeros,
                "right_x": vals_r, "right_y": vals_r, "right_z": vals_r,
                "right_current": [1.5 + 0.1 * random.gauss(0, 1) for _ in vals_r],
                "left_batch_id": -1,
                "right_batch_id": rbid,
                "broadcast_seq": bseq,
            }))
            bseq += 1
            t_right += batch_size * dt
            await asyncio.sleep(0.1)

        # Phase 2: 左右同时 5s
        print("[Phase2] 左右同时采集 50 批 (~5s)")
        t_left = 0.0
        for _ in range(50):
            lbid += 1
            rbid += 1
            t0_l = t_left
            t0_r = t_right
            times_l = [t0_l + i * dt for i in range(batch_size)]
            times_r = [t0_r + i * dt for i in range(batch_size)]
            vals_l = [math.sin(2 * math.pi * 50 * tt) * 0.6 + random.gauss(0, 0.1) for tt in times_l]
            vals_r = [math.sin(2 * math.pi * 80 * tt) * 0.5 + random.gauss(0, 0.1) for tt in times_r]
            await websocket.send(json.dumps({
                "type": "data_batch",
                "time": times_l,
                "left_x": vals_l, "left_y": vals_l, "left_z": vals_l,
                "left_current": [1.8 + 0.1 * random.gauss(0, 1) for _ in vals_l],
                "right_x": vals_r, "right_y": vals_r, "right_z": vals_r,
                "right_current": [1.5 + 0.1 * random.gauss(0, 1) for _ in vals_r],
                "left_batch_id": lbid,
                "right_batch_id": rbid,
                "broadcast_seq": bseq,
            }))
            bseq += 1
            t_left += batch_size * dt
            t_right += batch_size * dt
            await asyncio.sleep(0.1)

        # 结果
        await websocket.send(json.dumps({
            "type": "result", "side": "right", "result": "OK", "score": 0.95, "message": "右侧合格"}))
        await websocket.send(json.dumps({
            "type": "result", "side": "left", "result": "NG", "score": 0.30, "message": "左侧不合格"}))

        print("[完成] 80 批发送完毕")
        await asyncio.sleep(60)

    except websockets.exceptions.ConnectionClosed:
        pass


async def main():
    async with websockets.serve(handler, "0.0.0.0", 8081):
        print("=" * 55)
        print("[Mock Staggered] ws://localhost:8081 (batch_id 版)")
        print("Phase1: 仅右侧 30 批 → Phase2: 左右同时 50 批")
        print("=" * 55)
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[退出]")
