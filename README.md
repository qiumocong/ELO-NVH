# ELO-NVH 振动质检系统

ELO-NVH 是一套面向工业现场的双工位振动质检软件，包含 PyQt5 桌面前端、WebSocket 实时数据服务、NI-DAQmx 数据采集、三菱 PLC 流程控制和模型推理。原有模块和 WebSocket 消息协议保持不变；在此基础上增加了统一配置、日志轮转、可配置数据目录和 Windows exe 打包入口。

## 目录

```text
qianduan/             PyQt5 前端与标注工具
websocket_backend/    WebSocket、PLC、NI 采集、推理与保存
app_config.py         运行时 JSON 配置与日志
app/desktop_app.py    单进程桌面启动器
run_backend.py        仅启动后端的入口
packaging/yanpu.spec  PyInstaller 配置
packaging/yanpu.iss   Inno Setup 安装程序定义
build_windows.ps1     Windows 构建脚本
build_installer.ps1   一键构建应用和安装程序
build_light.ps1       一键构建 CPU 轻量发布版
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

产物为 `dist\ELO-NVH\ELO-NVH.exe`；发布时应复制整个 `dist\ELO-NVH` 目录。exe 首次启动会在 `ELO-NVH.exe` 同一目录创建 `config.json`、`logs`、`data` 和模型目录。若需调试控制台，当前 spec 已保留控制台窗口，便于查看 PLC/采集错误。

### 轻量发布版

生产发布使用独立的 CPU-only PyTorch 环境，避免把约 4 GB 的 CUDA 运行库带入安装包。首次构建轻量环境：

```powershell
uv venv .venv-release --python 3.8
uv pip install --python .venv-release\Scripts\python.exe --index-strategy unsafe-best-match `
  --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple `
  "torch==2.0.1+cpu"
uv pip install --python .venv-release\Scripts\python.exe "pyinstaller>=6.20.0" "fastapi>=0.124.4" "matplotlib>=3.7.5" "nidaqmx>=1.0.2" "numpy>=1.24.4" "openpyxl>=3.1.5" "pandas>=2.0.3" "pymcprotocol>=0.3.0" "pyqt5>=5.15.11" "pyqtgraph>=0.13.3" "python-multipart>=0.0.20" "soundfile>=0.13.1" "tqdm>=4.67.3" "uvicorn[standard]>=0.33.0" "websockets>=13.1" "scipy>=1.10.1"
```

然后使用发布环境构建：

```powershell
.\build_windows.ps1 -PythonPath .\.venv-release\Scripts\python.exe
.\build_installer.ps1 -Version 0.1.1 -PythonPath .\.venv-release\Scripts\python.exe -SkipAppBuild
# 后续发布可直接使用：
.\build_light.ps1 -Version 0.1.1
```

轻量版仍使用 CPU 推理，功能和模型不变；原 `.venv` CUDA 环境继续用于训练，不参与发布包。

## 生成安装程序

安装程序使用 Inno Setup 6，将完整的 `dist\ELO-NVH` 目录封装成 Windows 安装 EXE。先安装 [Inno Setup](https://jrsoftware.org/isinfo.php)，然后在项目根目录执行：

```powershell
.\build_installer.ps1
```

脚本会先重新构建 PyInstaller 应用，再生成 `dist\installer\ELO-NVH-Setup-0.1.1.exe`。指定版本号并跳过应用重构建的示例：

```powershell
.\build_installer.ps1 -Version 1.0.0
.\build_installer.ps1 -Version 1.0.0 -SkipAppBuild
```

安装包使用 Inno Setup 的高压缩模式。当前 CPU 轻量版小于 GitHub 的 2 GB 单文件限制，因此会生成一个完整的 `ELO-NVH-Setup-版本号.exe`，不需要 `.bin` 分卷；用户直接双击该文件即可安装。若未来发布内容超过单文件限制，再按 Inno Setup 配置启用分卷，并将所有分卷与主程序一起发布。

可使用以下命令生成校验值，并将输出粘贴到 Release 说明中：

```powershell
Get-FileHash .\dist\installer\ELO-NVH-Setup-0.1.1* -Algorithm SHA256
```

安装器默认安装到 `%LOCALAPPDATA%\Programs\ELO-NVH`，无需管理员权限；也可以在安装向导中选择其他目录。安装后从开始菜单或桌面快捷方式启动。卸载程序不会删除 `config.json`、`logs`、`data` 和模型文件，便于保留生产记录和升级恢复。

## 配置与数据

首次运行会在 `ELO-NVH.exe` 同目录生成 `config.json`。前端左侧“系统设置”统一包含“通信设置”“存储设置”“显示设置”和“软件更新”四个分页，可修改 WebSocket 地址、PLC 地址和端口、日志目录、训练数据目录、新格式数据目录、新格式保存开关、振动图 Y 轴范围及数据缩放比例。模型目录固定为安装目录下的 `logs\\models`，界面只读显示，不允许修改；已有模型会随安装包部署。通信和后端存储参数保存后重启生效，显示设置会立即应用；缩放只影响界面显示，不改变原始数据。

日志文件为 `yanpu.log`，单文件 10 MB，保留 5 个轮转文件。原有旧格式数据和新格式 CSV/PNG/WAV 数据结构均保留。

## 工程约束

- 生产部署前确认 NI-DAQmx、PLC 网络和模型文件可用。
- 修改端口后重启桌面程序，使后端和前端重新建立连接。
- 设置目录必须具备读写权限；保存路径不可使用网络断开时不可用的临时盘。
- 训练请使用 `websocket_backend/train_from_saved.py`，不会在检测启动时自动训练。
- 可执行 `ELO-NVH.exe --ni-self-test` 验证目标计算机的 NI-DAQmx 驱动能否创建任务；此检查不启动 PLC 或采集流程。

## 软件更新

在“系统设置 → 软件更新”中点击“打开更新检查”。程序会查询项目 GitHub Release，下载当前版本对应的安装包以及可能存在的 `.bin` 分卷，下载完成后校验并启动安装程序。安装升级不会删除 `config.json`、日志、采集数据或 `logs\\models` 中的模型。发布新版本时，Release 至少上传安装包 `.exe`；若存在分卷，则需将全部分卷一起上传，并保持原始文件名。

发布新版本前，将 `app/version.py` 中的 `APP_VERSION` 和 `pyproject.toml` 版本改为同一个版本号，再执行 `.\build_installer.ps1 -Version 1.0.1`，最后创建同名的 GitHub Release 标签（例如 `v1.0.1`）。
