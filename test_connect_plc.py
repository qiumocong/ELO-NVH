import pymcprotocol


def string_to_words(text):
    """
    将 ASCII 字符串转换为 PLC 可接收的 16 位整数列表 (小端模式)
    """
    # 如果字符串长度为奇数，在末尾补一个空字符(0x00)，以凑齐完整的 16 位字
    if len(text) % 2 != 0:
        text += '\x00'

    words = []
    for i in range(0, len(text), 2):
        # 取两个相邻的字符计算 ASCII 值
        low_byte = ord(text[i])
        high_byte = ord(text[i + 1])
        # 将两个 8 位字符合并成一个 16 位的字
        words.append(low_byte | (high_byte << 8))
    return words


def words_to_string(words):
    """
    将从 PLC 读取的 16 位整数列表解析还原为字符串 (小端模式)
    """
    text = ""
    for word in words:
        low_byte = word & 0xFF
        high_byte = (word >> 8) & 0xFF

        # 遇到结束符(0x00)时跳过，否则拼接还原字符
        if low_byte != 0:
            text += chr(low_byte)
        if high_byte != 0:
            text += chr(high_byte)

    return text.strip('\x00')


def slmp_comprehensive_demo():
    slmp_client = pymcprotocol.Type3E()
    slmp_client.setaccessopt(commtype="binary")

    plc_ip = "192.168.3.124"
    plc_port = 1025

    try:
        slmp_client.connect(plc_ip, plc_port)
        print("✅ SLMP 连接成功，开始全面测试！\n")

        # ==========================================
        # 测试 1: 单字整数测试 (原有功能)
        # ==========================================
        print("--- [测试 1: 整数读写] ---")
        reg_int = "D200"
        test_val = 1
        slmp_client.batchwrite_wordunits(headdevice=reg_int, values=[test_val])
        print(f"👉 发送: 向 {reg_int} 写入整数 [{test_val}]")

        read_int = slmp_client.batchread_wordunits(headdevice=reg_int, readsize=1)
        print(f"👈 接收: 从 {reg_int} 读取整数 [{read_int[0]}]\n")

        # ==========================================
        # 测试 2: 字符串数据测试 (新增功能)
        # ==========================================
        print("--- [测试 2: 字符串读写] ---")
        reg_str = "D300"
        test_string = "SN-2026-X9"

        # 1. 打包：将字符串转为 PLC 需要的 Word 列表
        words_to_send = string_to_words(test_string)
        write_size = len(words_to_send)

        # 2. 发送字符串数据
        slmp_client.batchwrite_wordunits(headdevice=reg_str, values=words_to_send)
        print(f"👉 发送: 向 {reg_str} 起始地址写入字符串 '{test_string}' (占用了 {write_size} 个寄存器：{words_to_send})")

        # 3. 接收并解包：读取相同长度的寄存器并还原为字符串
        # 注意：实际场景中，您可能需要读取一个固定长度(比如 10个字)
        read_words = slmp_client.batchread_wordunits(headdevice=reg_str, readsize=write_size)
        decoded_string = words_to_string(read_words)
        print(f"👈 接收: 从 {reg_str} 读取原始字 {read_words}，解析为字符串: '{decoded_string}'\n")

        # ==========================================
        # 结果校验
        # ==========================================
        if test_val == read_int[0] and test_string == decoded_string:
            print("🎉 所有读写测试通过，数据校验完全一致！")
        else:
            print("⚠️ 测试出现数据不一致，请检查！")

    except Exception as e:
        print(f"❌ SLMP 通信失败: {e}")

    finally:
        slmp_client.close()
        print("\n🔒 连接已安全关闭。")


if __name__ == "__main__":
    slmp_comprehensive_demo()