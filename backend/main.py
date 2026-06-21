import time
import os
import numpy as np
import pandas as pd
from datetime import datetime
from config import *
from plc_comm import PLCClient
from data_acquisition import DataAcquisition
from model_inference import load_model, preprocess_data, predict

def save_data_to_csv(t, data_8ch, barcode, save_dir, label=None):
    """保存采集数据到 CSV，文件名含时间戳和条码"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label_str = "OK" if label == 1 else "NG" if label == 0 else "Unknown"
    filename = f"{timestamp}_{barcode}_{label_str}.csv"
    filepath = os.path.join(save_dir, filename)

    # 构建 DataFrame，列名：time, ax, ay, az, ... 可根据需要调整
    df = pd.DataFrame()
    df["time"] = t
    # 默认只保存三轴（模型输入）和其他通道（可选）
    # 这里保存全部 8 通道
    for i in range(8):
        df[f"ch{i}"] = data_8ch[i, :]
    df.to_csv(filepath, index=False)
    print(f"[保存] 数据已保存至 {filepath}")
    return filepath

def main():
    # 初始化 PLC
    plc = PLCClient(PLC_IP, PLC_PORT)
    plc.connect()

    # 初始化数据采集器
    daq = DataAcquisition({
        "SAMPLE_RATE": SAMPLE_RATE,
        "CHUNK_SAMPLES": CHUNK_SAMPLES,
        "CH_9234": CH_9234,
        "CH_9239": CH_9239,
        "RANGE_9234": RANGE_9234,
        "RANGE_9239": RANGE_9239,
        "INPUT_CHANNEL_INDICES": INPUT_CHANNEL_INDICES,
        "PLOT_ENABLE": PLOT_ENABLE
    })

    # 加载模型（自动模式）
    model = None
    if MODE == "auto":
        model = load_model(MODEL_PATH, MODEL_IN_CH, MODEL_NUM_CLASSES, DEVICE)
        print("[模型] 加载完成")

    # 主循环状态机
    print("[主程序] 等待 PLC 就绪 (Step=100)...")
    while True:
        step = plc.read_word(PLC_STEP_REG)
        print(f"[PLC Step] {step}")

        # ---------- Step 100: 准备就绪 ----------
        if step == STEP_READY:
            # 读取条码
            barcode = plc.read_barcode(PLC_BARCODE_REG)
            print(f"[条码] {barcode}")
            # PC 回复就绪
            plc.write_word(PC_STEP_REG, STEP_READY)
            print("[PC] 已就绪")

        # ---------- Step 200: 开始测试 ----------
        elif step == STEP_TEST_START:
            print("[开始采集]")
            daq.start()
            # PC 确认开始（可选）
            plc.write_word(PC_STEP_REG, STEP_TEST_START)

        # ---------- Step 300: 第一段结束（仅握手） ----------
        elif step == STEP_TEST_FIRST_END:
            print("[第一段结束] PC 确认")
            plc.write_word(PC_STEP_REG, STEP_TEST_FIRST_END)

        # ---------- Step 400: 第二段开始（仅握手） ----------
        elif step == STEP_TEST_SECOND_START:
            print("[第二段开始] PC 确认")
            plc.write_word(PC_STEP_REG, STEP_TEST_SECOND_START)

        # ---------- Step 900: 全部结束，处理数据 ----------
        elif step == STEP_TEST_END:
            print("[测试结束] 停止采集，处理数据...")
            t, data_8ch = daq.stop()
            if t.size == 0:
                print("[警告] 未采集到数据")
                plc.write_word(PC_STEP_REG, STEP_TEST_END)
                continue

            # 根据模式执行不同逻辑
            if MODE == "auto":
                # 自动检测
                data_tensor = preprocess_data(data_8ch, INPUT_CHANNEL_INDICES)
                pred = predict(model, data_tensor, DEVICE)
                label = pred  # 0=OK, 1=NG
                result_code = 1 if label == 0 else 2   # 1 OK, 2 NG
                print(f"[推理结果] {'OK' if label==0 else 'NG'} (code={result_code})")

                # 保存数据到对应目录
                save_dir = os.path.join(DATA_SAVE_DIR, OK_DIRNAME if label==0 else NG_DIRNAME)
                save_data_to_csv(t, data_8ch, barcode, save_dir, label)

                # 发送结果给 PLC
                plc.write_word(PLC_RESULT_REG, result_code)
                print("[PLC] 结果已发送")

            elif MODE == "manual":
                # 人工标注：等待 PLC 写入判定结果 (1=OK, 2=NG)
                print("[人工模式] 等待 PLC 发送判定结果...")
                timeout = 30
                start_wait = time.time()
                result_code = None
                while time.time() - start_wait < timeout:
                    val = plc.read_word(PLC_MANUAL_RESULT_REG)
                    if val in (1, 2):
                        result_code = val
                        break
                    time.sleep(0.5)
                if result_code is None:
                    print("[错误] 超时未收到人工判定结果，默认 NG")
                    result_code = 2
                label = 0 if result_code == 1 else 1   # 转为 0=OK, 1=NG
                save_dir = os.path.join(DATA_SAVE_DIR, OK_DIRNAME if label==0 else NG_DIRNAME)
                save_data_to_csv(t, data_8ch, barcode, save_dir, label)
                print(f"[保存] 已保存为 {'OK' if label==0 else 'NG'}")

                # 回复 PLC 已完成
                plc.write_word(PC_STEP_REG, STEP_TEST_END)

            # 完成处理后，将 PC Step 置为 900 表示处理完毕（可选）
            # 此处也可等待 PLC 恢复到 100 再继续，或直接等待下一个指令
            print("[处理完成] 回到等待状态...")

        # 休眠避免过频轮询
        time.sleep(0.1)

    # 正常情况下不会执行到这里
    plc.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[中断] 程序退出")
    finally:
        # 确保资源释放
        if 'plc' in locals():
            plc.close()
        if 'daq' in locals():
            daq.stop()