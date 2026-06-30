"""
XXX 检测系统 — 程序入口

启动方式：
    python main.py                      # 用模拟数据
    python main.py --ws                 # WebSocket 连接后端
    python main.py --csv                # 读 data/ch0.csv 回放
    python main.py --csv path/to.csv   # 读指定 CSV
"""

import sys
import os
# 确保优先导入 qianduan/ 下的 config，而不是项目根目录的
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
from config import WS_URL, RECONNECT_INTERVAL


def main():
    app = QApplication(sys.argv)

    from PyQt5.QtGui import QFont
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()

    csv_idx = next((i for i, a in enumerate(sys.argv) if a == "--csv"), -1)
    if csv_idx >= 0:
        csv_path = sys.argv[csv_idx + 1] if csv_idx + 1 < len(sys.argv) and not sys.argv[csv_idx + 1].startswith("--") else "data/ch0.csv"
        cur_csv_idx = next((i for i, a in enumerate(sys.argv) if a == "--current-csv"), -1)
        cur_csv = sys.argv[cur_csv_idx + 1] if cur_csv_idx >= 0 and cur_csv_idx + 1 < len(sys.argv) and not sys.argv[cur_csv_idx + 1].startswith("--") else None
        from csv_data_source import CsvDataSource
        source = CsvDataSource(csv_path=csv_path, current_csv_path=cur_csv, interval_ms=50, batch_size=100)
    elif "--ws" in sys.argv:
        from websocket_client import WebSocketClient
        source = WebSocketClient(url=WS_URL, reconnect_interval=RECONNECT_INTERVAL)
    else:
        from mock_data import MockDataSource
        source = MockDataSource(interval_ms=50, batch_size=10)

    window.connect_data_source(source)
    source.start()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
