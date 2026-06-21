import pymcprotocol
import time

# ==========================================
# 寄存器地址配置
# ==========================================
REG_PLC_STEP = "D100"  # PLC Step 地址 (字)
REG_PC_STEP = "D101"  # PC Step 地址 (字)
REG_SPEC_DATA = "D200"  # 产品规格数据地址 (字/多个字)
REG_BARCODE = "D210"  # 条码数据起始地址 (字/多个字)
REG_TESTING_BIT = "M10"  # PLC正在测试信号 (位)
REG_HEARTBEAT = "M11"  # PC心跳脉冲信号 (位)

# ==========================================
# 连接设置
# ==========================================
PLC_IP = "192.168.1.100"
PLC_PORT = 5000

def process_judgment_and_save(is_auto=True, is_ok=True):
    """
    处理判定并保存数据（对应流程图中的 PS 备注）
    """
    if is_auto:
        # 自动判定时：OK输出1，NG输出2
        judgment_result = 1 if is_ok else 2
        print(f"✅ [自动判定] 结果: {judgment_result}，正在自动保存数据...")
        # TODO: 在此处添加将 judgment_result 发送给PLC或写入数据库的代码
    else:
        # 人工判定时：收到结果后保存数据
        print("🧑‍🔧 [人工判定] 收到人工判定结果，正在保存数据...")
        # TODO: 在此处添加保存数据的逻辑


def plc_interaction_loop():
    slmp_client = pymcprotocol.Type3E()
    slmp_client.setaccessopt(commtype="binary")

    plc_ip = "192.168.1.100"
    plc_port = 5000

    try:
        slmp_client.connect(plc_ip, plc_port)
        print("✅ SLMP 连接成功，开始监听流程...")

        last_plc_step = -1
        heartbeat_toggle = 0

        while True:
            # ---------------------------------------------------------
            # 0. PC实时输出脉冲信号 (心跳，通讯无异常信号)
            # ---------------------------------------------------------
            heartbeat_toggle = 1 if heartbeat_toggle == 0 else 0
            slmp_client.batchwrite_bitunits(headdevice=REG_HEARTBEAT, values=[heartbeat_toggle])

            # ---------------------------------------------------------
            # 读取当前 PLC Step 和 测试信号
            # ---------------------------------------------------------
            plc_step_data = slmp_client.batchread_wordunits(headdevice=REG_PLC_STEP, readsize=1)
            current_plc_step = plc_step_data[0]

            # ---------------------------------------------------------
            # 状态机逻辑：只在 PLC Step 发生变化时触发动作，避免重复写入
            # ---------------------------------------------------------
            if current_plc_step != last_plc_step:
                print(f"🔄 检测到状态切换: PLC Step = {current_plc_step}")

                if current_plc_step == 100:
                    # 步骤 4: PLC准备就绪 (PLC Step=100)
                    print("--- 步骤 1 & 2: 读取规格和条码 ---")
                    spec_data = slmp_client.batchread_wordunits(headdevice=REG_SPEC_DATA, readsize=5)  # 假设读5个字
                    barcode_data = slmp_client.batchread_wordunits(headdevice=REG_BARCODE, readsize=5)
                    print(f"   规格数据: {spec_data}, 条码数据: {barcode_data}")

                    # 步骤 3: 检查正在测试信号 (可选，用于UI显示)
                    test_bit = slmp_client.batchread_bitunits(headdevice=REG_TESTING_BIT, readsize=1)
                    print(f"   当前测试信号状态: {test_bit[0]}")

                    # 步骤 5: PC准备就绪 (PC Step=100)
                    slmp_client.batchwrite_wordunits(headdevice=REG_PC_STEP, values=[100])
                    print("👉 步骤 5 执行: 已写入 PC Step = 100")

                elif current_plc_step == 200:
                    # 步骤 6: PLC第一段测试开始
                    print("⚙️ PLC第一段测试正在进行中...")

                elif current_plc_step == 300:
                    # 步骤 7: PLC第一段测试结束
                    # 步骤 8: PC收到第一段测试结束 (PC Step=300)
                    slmp_client.batchwrite_wordunits(headdevice=REG_PC_STEP, values=[300])
                    print("👉 步骤 8 执行: 已写入 PC Step = 300")

                elif current_plc_step == 400:
                    # 步骤 9: PLC第二段测试开始
                    print("⚙️ PLC第二段测试正在进行中...")

                elif current_plc_step == 900:
                    # 步骤 10: PLC第二段测试结束
                    # 步骤 11: PC收到第二段测试结束 (PC Step=900)
                    slmp_client.batchwrite_wordunits(headdevice=REG_PC_STEP, values=[900])
                    print("👉 步骤 11 执行: 已写入 PC Step = 900")

                    # 测试流程结束，执行判定和保存逻辑（对应图中 PS 备注）
                    process_judgment_and_save(is_auto=True, is_ok=True)

                # 更新上一次的步骤记录
                last_plc_step = current_plc_step

            # 每次循环稍微暂停，避免占用过高CPU并控制心跳频率 (如100ms)
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 收到中断信号，程序退出。")
    except Exception as e:
        print(f"❌ SLMP 通信发生异常: {e}")
    finally:
        slmp_client.close()
        print("🔒 连接已安全关闭。")


if __name__ == "__main__":
    plc_interaction_loop()