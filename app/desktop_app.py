import json
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from urllib import error, request

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from app.runtime_config import load_runtime_config


class DetectionDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("振动噪声检测")
        self.runtime_config = load_runtime_config()
        self.backend_url = f"http://{self.runtime_config.backend_host}:{self.runtime_config.backend_port}/detect"
        self.request_timeout_sec = self.runtime_config.backend_request_timeout_sec

        self.status_var = tk.StringVar(value="待机")
        self.result_var = tk.StringVar(value="结果：--")
        self.confidence_var = tk.StringVar(value="置信度：--")
        self.time_var = tk.StringVar(value="时间：--")
        self.command_var = tk.StringVar(value="START_DETECT")
        self.excel_path_var = tk.StringVar(value=str(self.runtime_config.excel_path))

        self._build_layout()

    def _build_layout(self):
        ctrl_frame = ttk.Frame(self.root, padding=10)
        ctrl_frame.pack(fill=tk.X)

        ttk.Label(ctrl_frame, text="PLC指令").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(ctrl_frame, textvariable=self.command_var, width=25).grid(row=0, column=1, sticky=tk.W, padx=6)

        ttk.Label(ctrl_frame, text="Excel路径").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(ctrl_frame, textvariable=self.excel_path_var, width=80).grid(row=1, column=1, sticky=tk.W, padx=6, pady=(6, 0))

        self.detect_btn = ttk.Button(ctrl_frame, text="发送指令并检测", command=self._on_detect_click)
        self.detect_btn.grid(row=0, column=2, rowspan=2, padx=(10, 0))

        status_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        status_frame.pack(fill=tk.X)
        ttk.Label(status_frame, textvariable=self.status_var).pack(anchor=tk.W)
        ttk.Label(status_frame, textvariable=self.result_var).pack(anchor=tk.W)
        ttk.Label(status_frame, textvariable=self.confidence_var).pack(anchor=tk.W)
        ttk.Label(status_frame, textvariable=self.time_var).pack(anchor=tk.W)

        fig = Figure(figsize=(8, 4), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_title("振动波形")
        self.ax.set_xlabel("time")
        self.ax.set_ylabel("amplitude")
        self.canvas = FigureCanvasTkAgg(fig, master=self.root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _on_detect_click(self):
        self.detect_btn.state(["disabled"])
        self.status_var.set("检测中...")
        threading.Thread(target=self._run_detection, daemon=True).start()

    def _run_detection(self):
        payload = {
            "command": self.command_var.get().strip() or "START_DETECT",
            "excel_path": self.excel_path_var.get().strip(),
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.backend_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self.request_timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            self.root.after(0, lambda: self._on_error(f"请求失败: {exc}"))
            return
        except Exception as exc:
            self.root.after(0, lambda: self._on_error(f"未知异常: {exc}"))
            return

        self.root.after(0, lambda: self._update_ui(data))

    def _on_error(self, msg: str):
        self.status_var.set("失败")
        self.detect_btn.state(["!disabled"])
        messagebox.showerror("检测失败", msg)

    def _update_ui(self, result: dict):
        self.detect_btn.state(["!disabled"])
        if not result.get("ok"):
            self.status_var.set(f"失败：{result.get('error_code', 'UNKNOWN')}")
            messagebox.showerror("检测失败", result.get("message", "未知错误"))
            return

        det = result["result"]
        waveform = result["waveform"]
        label = det["label"]
        confidence = det["confidence"]
        ts = result.get("timestamp", datetime.now().isoformat())
        try:
            ts_display = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            ts_display = ts

        self.status_var.set("检测完成")
        self.result_var.set(f"结果：{label}")
        self.confidence_var.set(f"置信度：{confidence * 100:.2f}%")
        self.time_var.set(f"时间：{ts_display}")

        self.ax.clear()
        self.ax.plot(waveform["time"], waveform["ax"], label="ax", linewidth=1)
        self.ax.plot(waveform["time"], waveform["ay"], label="ay", linewidth=1)
        self.ax.plot(waveform["time"], waveform["az"], label="az", linewidth=1)
        self.ax.set_title("振动波形")
        self.ax.set_xlabel("time")
        self.ax.set_ylabel("amplitude")
        self.ax.legend(loc="upper right")
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    root.geometry("980x700")
    app = DetectionDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
