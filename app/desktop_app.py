import json
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from urllib import error, request

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from app.runtime_config import load_runtime_config


UI_FONT_FAMILY = "Segoe UI"


class DetectionDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("振动噪声检测")
        self.root.configure(bg="#F3F5F9")
        self.runtime_config = load_runtime_config()
        self.backend_url = f"http://{self.runtime_config.backend_host}:{self.runtime_config.backend_port}/detect"
        self.request_timeout_sec = self.runtime_config.backend_request_timeout_sec

        self.status_var = tk.StringVar(value="待机")
        self.result_var = tk.StringVar(value="结果：--")
        self.confidence_var = tk.StringVar(value="置信度：--")
        self.time_var = tk.StringVar(value="时间：--")
        self.command_var = tk.StringVar(value="START_DETECT")
        self.excel_path_var = tk.StringVar(value=str(self.runtime_config.excel_path))

        self._configure_style()
        self._build_layout()

    def _configure_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Card.TLabelframe", background="#FFFFFF")
        style.configure("Card.TLabelframe.Label", font=(UI_FONT_FAMILY, 11, "bold"))
        style.configure("TFrame", background="#F3F5F9")
        style.configure("TLabel", background="#F3F5F9", font=(UI_FONT_FAMILY, 10))
        style.configure("Title.TLabel", font=(UI_FONT_FAMILY, 16, "bold"))
        style.configure("Value.TLabel", font=(UI_FONT_FAMILY, 11))
        style.configure("TButton", font=(UI_FONT_FAMILY, 10), padding=6)
        style.configure("Accent.TButton", font=(UI_FONT_FAMILY, 10, "bold"), padding=8)
        style.configure("TEntry", padding=5)

    def _build_layout(self):
        main_frame = ttk.Frame(self.root, padding=14)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="振动噪声检测", style="Title.TLabel").pack(anchor=tk.W, pady=(0, 10))

        ctrl_frame = ttk.LabelFrame(main_frame, text="检测配置", style="Card.TLabelframe", padding=12)
        ctrl_frame.pack(fill=tk.X)
        ctrl_frame.columnconfigure(1, weight=1)

        ttk.Label(ctrl_frame, text="PLC指令").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(ctrl_frame, textvariable=self.command_var, width=28).grid(row=0, column=1, sticky=tk.W, padx=8)

        ttk.Label(ctrl_frame, text="Excel/CSV文件").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(ctrl_frame, textvariable=self.excel_path_var).grid(
            row=1, column=1, sticky=tk.EW, padx=8, pady=(8, 0)
        )
        ttk.Button(ctrl_frame, text="选择文件", command=self._choose_excel_file).grid(
            row=1, column=2, padx=(0, 8), pady=(8, 0)
        )

        self.detect_btn = ttk.Button(ctrl_frame, text="开始检测", style="Accent.TButton", command=self._on_detect_click)
        self.detect_btn.grid(row=0, column=2, padx=(0, 8))

        status_frame = ttk.LabelFrame(main_frame, text="检测状态", style="Card.TLabelframe", padding=12)
        status_frame.pack(fill=tk.X)
        ttk.Label(status_frame, textvariable=self.status_var, style="Value.TLabel").pack(anchor=tk.W)
        ttk.Label(status_frame, textvariable=self.result_var, style="Value.TLabel").pack(anchor=tk.W)
        ttk.Label(status_frame, textvariable=self.confidence_var, style="Value.TLabel").pack(anchor=tk.W)
        ttk.Label(status_frame, textvariable=self.time_var, style="Value.TLabel").pack(anchor=tk.W)

        fig = Figure(figsize=(8, 4), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_title("振动波形")
        self.ax.set_xlabel("time")
        self.ax.set_ylabel("amplitude")
        self.canvas = FigureCanvasTkAgg(fig, master=main_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=(10, 0))

    def _choose_excel_file(self):
        path = filedialog.askopenfilename(
            title="选择检测文件",
            filetypes=[
                ("Data files", "*.xlsx *.xls *.csv"),
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.excel_path_var.set(path)

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
    root.geometry("1100x760")
    root.minsize(980, 700)
    app = DetectionDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
