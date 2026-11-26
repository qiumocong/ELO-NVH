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

版本集中定义在仓库根目录的 `.app_version`。构建时自动同步项目元数据并把版本写入软件界面和安装包名称：

```powershell
Get-Content .\.app_version
.\build_light.ps1
```

新版本可编辑 `.app_version` 后运行构建脚本；也可以用 `-Version 0.1.6` 覆盖文件并构建，此后不带参数运行都会使用该版本。轻量版仍使用 CPU 推理；原 `.venv` CUDA 环境不参与发布包。

## 生成安装程序

安装程序使用 Inno Setup 6，将完整的 `dist\ELO-NVH` 目录封装成 Windows 安装 EXE。先安装 [Inno Setup](https://jrsoftware.org/isinfo.php)，然后在项目根目录执行：

```powershell
.\build_installer.ps1
```

脚本会先重新构建 PyInstaller 应用，再生成使用 `.app_version` 命名的安装包。指定版本并跳过应用重构建的示例：

```powershell
.\build_installer.ps1 -Version 1.0.0
.\build_installer.ps1 -Version 1.0.0 -SkipAppBuild
```

安装包使用 Inno Setup 的高压缩模式。当前 CPU 轻量版小于 GitHub 的 2 GB 单文件限制，因此会生成一个完整的 `ELO-NVH-Setup-版本号.exe`，不需要 `.bin` 分卷；用户直接双击该文件即可安装。若未来发布内容超过单文件限制，再按 Inno Setup 配置启用分卷，并将所有分卷与主程序一起发布。

可使用以下命令生成校验值，并将输出粘贴到 Release 说明中：

```powershell
Get-FileHash .\dist\installer\ELO-NVH-Setup-*.exe -Algorithm SHA256
```

安装器默认安装到 `%LOCALAPPDATA%\Programs\ELO-NVH`，无需管理员权限；也可以在安装向导中选择其他目录。安装后从开始菜单或桌面快捷方式启动。卸载程序不会删除 `config.json`、`logs`、`data` 和模型文件，便于保留生产记录和升级恢复。

## 配置与数据

首次运行会在 `ELO-NVH.exe` 同目录生成 `config.json`。日志、训练数据、新格式数据和模型路径以安装目录为基准保存为相对路径，程序独立于当前工作目录解析它们。旧配置中指向现存目录的绝对路径会转换为相对路径；失效路径会回退为默认值。系统设置可修改通信参数、数据路径和图表显示；模型目录固定为 `logs/models`。

日志文件为 `yanpu.log`，单文件 10 MB，保留 5 个轮转文件。原有旧格式数据和新格式 CSV/PNG/WAV 数据结构均保留。

## 工程约束

### 新电脑构建与部署（0.1.5）

- **仅构建安装包**：需要 Python 发布环境、PyInstaller 和 Inno Setup 6；不需要安装 NI SDK、LabVIEW 或 NI-DAQmx 驱动。使用 `.\build_light.ps1` 构建 CPU 发布版，版本取自 `.app_version`。
- **模拟运行**：安装后执行 `ELO-NVH.exe --mock`，无需 NI 驱动、采集卡或 PLC。
- **真实采集**：运行电脑必须单独安装 [NI-DAQmx 驱动](https://www.ni.com/en/support/downloads/drivers/download.ni-daq-mx.html)，选择支持目标 Windows 和 cDAQ 硬件的版本，安装后按提示重启。无需额外安装完整的 LabVIEW 或开发 SDK；安装包已包含 Python 的 `nidaqmx` 封装，但不包含系统驱动。
- 在 NI MAX 中确认设备能通过自检，且设备名/通道与 `websocket_backend/config.py` 一致：`cDAQ1Mod1/ai0:2`、`cDAQ1Mod2/ai0:2` 和 `cDAQ1Mod3/ai0:3`。在系统设置中确认 PLC 地址、端口、日志和数据路径符合新电脑现场配置。
- 执行 `ELO-NVH.exe --self-test` 检查发布包依赖、全部模型的 CPU 推理、界面组件和双工位模拟数据处理；此模式不连接 NI 或 PLC，也不代表硬件联调通过。执行 `ELO-NVH.exe --ni-self-test` 单独验证系统驱动能创建并关闭 NI 任务。

- 生产部署前确认 NI-DAQmx、PLC 网络和模型文件可用。
- 修改端口后重启桌面程序，使后端和前端重新建立连接。
- 设置目录必须具备读写权限；保存路径不可使用网络断开时不可用的临时盘。
- 训练请使用 `websocket_backend/train_from_saved.py`，不会在检测启动时自动训练。
- 可执行 `ELO-NVH.exe --ni-self-test` 验证目标计算机的 NI-DAQmx 驱动能否创建任务；此检查不启动 PLC 或采集流程。

## 软件更新

在“系统设置 → 软件更新”中点击“打开更新检查”。程序会查询项目 GitHub Release，下载当前版本对应的安装包以及可能存在的 `.bin` 分卷，下载完成后校验并启动安装程序。安装升级不会删除 `config.json`、日志、采集数据或 `logs\\models` 中的模型。发布新版本时，Release 至少上传安装包 `.exe`；若存在分卷，则需将全部分卷一起上传，并保持原始文件名。

发布新版本时编辑 `.app_version` 并执行 `.\build_light.ps1`；构建脚本自动同步项目元数据，再生成 PyInstaller 程序和 Inno Setup 安装包。随后创建同版本的 GitHub Release 标签并上传对应安装包。

更新过程由独立更新进程完成：安装包先下载到 `%TEMP%\ELO-NVH-update-*`，主程序退出后，更新进程等待旧进程结束，使用静默参数运行安装器并安装到当前程序目录，最后重新启动同一目录下的 `ELO-NVH.exe`。更新诊断写入安装目录 `logs\update.log`；如果安装目录不可写，则写入 `%TEMP%\ELO-NVH-update.log`。旧版本的 v0.1.2 安装包曾只更新了安装器版本号，内部版本仍为 0.1.1，应使用修复后的新版本发布。
