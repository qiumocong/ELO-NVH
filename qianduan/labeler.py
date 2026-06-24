"""
数据集标注工具 — 程序入口

启动方式：
    python labeler.py          # 用模拟数据
    python labeler.py --ws     # 用真实 WebSocket
"""

import sys
from PyQt5.QtWidgets import QApplication
from ui.labeler_window import LabelerWindow
from config import WS_URL, RECONNECT_INTERVAL


def main():
    app = QApplication(sys.argv)

    from PyQt5.QtGui import QFont
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = LabelerWindow()

    from mock_data import MockDataSource
    source = MockDataSource(interval_ms=50, batch_size=10, auto_start=True)

    if "--ws" in sys.argv:
        from websocket_client import WebSocketClient
        source = WebSocketClient(url=WS_URL, reconnect_interval=RECONNECT_INTERVAL)

    window.connect_data_source(source)
    source.start()

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
