"""
XXX 检测系统 — 程序入口

启动方式：
    python main.py          # 用模拟数据（开发调试）
    python main.py --ws     # 用真实 WebSocket 连接后端
"""

import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
from config import WS_URL, RECONNECT_INTERVAL


def main():
    app = QApplication(sys.argv)

    from PyQt5.QtGui import QFont
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()

    from mock_data import MockDataSource
    source = MockDataSource(interval_ms=50, batch_size=10)

    if "--ws" in sys.argv:
        from websocket_client import WebSocketClient
        source = WebSocketClient(url=WS_URL, reconnect_interval=RECONNECT_INTERVAL)

    window.connect_data_source(source)
    source.start()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
