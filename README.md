# Yanpu 振动质检系统

Yanpu 是一套面向工业现场的双工位振动质检软件，包含 PyQt5 桌面前端、WebSocket 实时数据服务、NI-DAQmx 数据采集、三菱 PLC 流程控制和模型推理。原有模块和 WebSocket 消息协议保持不变；在此基础上增加了统一配置、日志轮转、可配置数据目录和 Windows exe 打包入口。

## 目录

```text
qianduan/             PyQt5 前端与标注工具
websocket_backend/    WebSocket、PLC、NI 采集、推理与保存
app_config.py         运行时 JSON 配置与日志
app/desktop_app.py    单进程桌面启动器
run_backend.py        仅启动后端的入口
packaging/yanpu.spec  PyInstaller 配置
build_windows.ps1     Windows 构建脚本
软件说明书.md         操作和部署说明
```

## 源码运行

建议使用 Python 3.10/3.11 64 位环境，并安装 NI-DAQmx 驱动。依赖可按 `pyproject.toml` 安装：

```powershell
python -m pip install -e .
python -m app.desktop_app --mock       # 无 PLC 时使用模拟数据
python -m app.desktop_app               # 连接本机 WebSocket 后端
python run_backend.py                   # 仅启动后端
```

## 构建 exe

在 Windows 开发机执行：

```powershell
.\build_windows.ps1
```

产物为 `dist\Yanpu\Yanpu.exe`；发布时应复制整个 `dist\Yanpu` 目录。exe 启动时会自动在 `%APPDATA%\Yanpu` 创建配置、日志、模型和数据目录，不要求把数据写入安装目录。若需调试控制台，当前 spec 已保留控制台窗口，便于查看 PLC/采集错误。

## 配置与数据

首次运行会生成 `%APPDATA%\Yanpu\config.json`。前端左侧“系统设置”可修改 WebSocket 地址、PLC 地址和端口、日志目录、训练数据目录、新格式数据目录、模型目录及新格式保存开关；保存后重启生效。原有“振动图设置”和“数据缩放”也会持久化。

日志文件为 `yanpu.log`，单文件 10 MB，保留 5 个轮转文件。原有旧格式数据和新格式 CSV/PNG/WAV 数据结构均保留。

## 工程约束

- 生产部署前确认 NI-DAQmx、PLC 网络和模型文件可用。
- 修改端口后重启桌面程序，使后端和前端重新建立连接。
- 设置目录必须具备读写权限；保存路径不可使用网络断开时不可用的临时盘。
- 训练请使用 `websocket_backend/train_from_saved.py`，不会在检测启动时自动训练。
