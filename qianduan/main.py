"""
XXX 检测系统 — 程序入口

这是整个程序的起点，做了以下事情：
1. 创建 PyQt5 应用
2. 创建主窗口
3. 选择数据源（模拟数据 或 真实 WebSocket）
4. 把数据源和窗口连接起来
5. 启动数据源，显示窗口

启动方式：

    python main.py          # 用模拟数据（开发调试）
    python main.py --ws     # 用真实 WebSocket 连接后端
"""

import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
from config import WS_URL, RECONNECT_INTERVAL


def main():
    # 1. 创建 PyQt5 应用实例（每个 PyQt5 程序必须有且只有一个 QApplication）
    app = QApplication(sys.argv)

    # 2. 设置全局字体为微软雅黑（Windows 中文字体）
    from PyQt5.QtGui import QFont
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 3. 创建主窗口
    window = MainWindow()

    # 4. 选择数据源
    # 默认使用模拟数据（开发调试用，不需要后端）
    # 如果命令行传了 --ws 参数，就用真实的 WebSocket 连接
    from mock_data import MockDataSource
    source = MockDataSource(interval_ms=50, batch_size=10)

    if "--ws" in sys.argv:
        from websocket_client import WebSocketClient
        source = WebSocketClient(url=WS_URL, reconnect_interval=RECONNECT_INTERVAL)

    # 5. 把数据源的信号连接到窗口的槽函数
    # 这样数据源收到数据时，窗口会自动更新
    window.connect_data_source(source)

    # 6. 启动数据源（模拟数据会等待用户选模型后才推送）
    source.start()

    # 7. 显示窗口，进入事件循环
    window.show()
    sys.exit(app.exec_())  # app.exec_() 启动事件循环，窗口会一直显示直到用户关闭


if __name__ == "__main__":
    main()
