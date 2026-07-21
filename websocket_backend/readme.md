# PLC + NI 振动信号采集与质检系统（后端）

本项目是一个面向工业质检的实时数据采集与推理系统，通过 **NI cDAQ** 采集加速度、电压、电流信号，与 **三菱 PLC** 进行 Modbus TCP 通信协调工位流程，并利用深度学习模型（1D-CNN）对振动信号进行实时缺陷判定。系统支持左右双工位独立采集、PLC 命令驱动、WebSocket 实时数据推送、模型管理与训练等功能。

---

## 目录
- [项目目录结构](#项目目录结构)
- [各文件功能说明](#各文件功能说明)
- [安装与运行](#安装与运行)
- [数据保存格式](#数据保存格式)
- [工作流程（自动模式）](#工作流程自动模式)
- [扩展与定制](#扩展与定制)
- [注意事项](#注意事项)

---

## 项目目录结构

```
.
├── config.py                # 全局配置文件（PLC地址、寄存器、NI通道、模型参数等）
├── plc_comm.py              # 三菱 PLC 通信封装（基于 pymcprotocol）
├── plc_manager.py           # PLC 连接单例管理（心跳、重连、带重试的操作封装）
├── heartbeat.py             # 心跳线程（周期性写入心跳寄存器）
├── shared_data_acquisition.py # NI DAQ 采集核心（双工位独立延迟、数据环形存储）
├── station_worker.py        # 工位流程控制器（等待PLC命令、触发采集、推理、保存数据）
├── model.py                 # 1D-CNN 模型定义
├── model_inference.py       # 模型加载与推理（按规格加载 .pth，预处理，预测）
├── train_from_saved.py      # 基于保存的 CSV 数据训练模型（支持规格自动分组）
├── websocket_server.py      # WebSocket 服务（推送实时数据、接收人工标注）
├── main.py                  # 程序入口（启动 WebSocket、PLC 管理器、双工位工作线程）
├── logs/                    # 自动生成的日志/模型目录（默认）
│   ├── models/              # 存储训练好的模型文件（规格名.pth）
│   └── saved_data/          # 旧格式保存的数据（按规格/OK_NG/条码）
└── D:/DATA/                 # 新格式保存目录（可配置，按年/月/日/OK_NG/条码/时分）
```

---

## 各文件功能说明

### `config.py`
- **所有可调参数集中管理**：
  - PLC IP/端口、寄存器地址（条码、命令、状态、结果等）。
  - 左右工位的 NI 通道映射（加速度、电压、电流）。
  - 采样率、块大小、最大采集时长、传感器量程。
  - 模型输入通道数、类别数、训练超参数。
  - 数据保存路径（旧格式 `./logs/saved_data` 和新格式 `D:/DATA`）。

### `plc_comm.py`
- 使用 `pymcprotocol` 实现与三菱 PLC 的 Modbus TCP 通信。
- 提供读写字寄存器、位寄存器（如 R30.1）、条码/规格字符串解析等功能。
- 是 PLC 通信的底层封装。

### `plc_manager.py`
- **单例模式**管理 PLC 连接，内部维护心跳线程（`_keepalive`）。
- 提供带自动重连和重试机制的读写方法（`_execute_with_retry`）。
- 封装了工位相关的便捷方法（`read_barcode`, `write_result`, `read_data_ready` 等）。
- 所有 PLC 操作通过该管理器调用，确保连接稳定。

### `heartbeat.py`
- 独立心跳线程，周期性地向 PLC 写入递增计数器（寄存器 `R999`）。
- 使用 `plc_manager` 的共享连接，不会额外创建连接。

### `shared_data_acquisition.py`
- **NI DAQ 采集单例**，使用 `nidaqmx` 同时采集 10 个通道（左右各 5 个）。
- 支持左右工位独立**延迟启动**（`START_DELAY` 可配置），用于消除启动冲击。
- 数据以环形缓冲区存储（最大 `MAX_COLLECT_TIME` 秒），每个工位独立维护样本计数。
- 提供 `get_data_slice(side, start, end)` 获取任意时间段数据。
- 采集时通过回调（`register_callback`）将实时数据块推送给 `websocket_server`。

### `station_worker.py`
- **工位流程控制核心**，每个工位（左/右）运行一个独立线程。
- 状态机流程：
  1. 等待 PLC 的 `READY` 命令或数据就绪信号（`data_ready_reg`）。
  2. 读取条码、规格、模式，加载对应模型（自动模式）。
  3. 等待 `START` 命令 → 启动采集（可延迟）。
  4. 等待 `FIRST_END` → 记录第一段结束样本索引，暂停推送。
  5. 等待 `SECOND_START` → 继续采集（不重置时间），恢复推送。
  6. 等待 `STOP` → 停止采集，获取两段数据拼接，执行推理。
  7. 将结果（OK/NG）写入 PLC，并保存数据（新旧两种格式）。
- 支持人工模式（通过 WebSocket 标注或 PLC 寄存器 `manual_result_reg`）。

### `model.py`
- 定义 1D-CNN 模型（`Accel1DCNN`），输入 (B, C, T)，输出 (B, 2)。
- 包含 stem（卷积+池化）、膨胀卷积块、全局平均池化、分类头。

### `model_inference.py`
- 缓存已加载的模型（按规格名）。
- `get_model_for_spec(spec_name)` 从 `MODEL_DIR` 加载对应的 `.pth` 文件，若无则尝试加载 `default.pth`。
- `preprocess(data, station_name)` 提取指定通道（默认 x,y,z）并转为 Tensor。
- `predict(model, tensor)` 返回预测类别和置信度。

### `train_from_saved.py`
- 从旧格式数据目录（`DATA_SAVE_DIR`）读取每个规格的数据。
- 自动划分训练/验证/测试集（分层抽样），训练并保存模型到 `MODEL_DIR`。
- 使用 `VibrationDataset` 支持变长序列（通过 collate 填充）。
- 输出分类报告和混淆矩阵。

### `websocket_server.py`
- 基于 `websockets` 库提供 WebSocket 服务（端口 8081）。
- 实时广播采集到的数据块（左右工位的 x/y/z/电流），供前端波形显示。
- 接收前端发来的“人工标注”消息（`{"type":"label", "side":"left", "label":1}`）。
- 推送工位信息（条码/规格/模式）、检测结果（OK/NG/置信度）。
- 维护 `pending_label` 供 `StationWorker` 轮询获取人工判定。

### `main.py`
- 启动 WebSocket 服务线程。
- 创建 `PLCManager` 单例，创建左右两个 `StationWorker` 实例。
- 主线程阻塞，等待 Ctrl+C 中断，优雅关闭所有线程和资源。

---

## 安装与运行

### 环境要求
- Python 3.8+
- NI-DAQmx 驱动（用于 `nidaqmx`）
- 三菱 PLC（支持 Modbus TCP）

### 安装依赖
```bash
pip install nidaqmx pymcprotocol torch pandas numpy scikit-learn matplotlib scipy websockets tqdm
```

### 配置
- 修改 `config.py` 中的 PLC IP/端口、NI 通道名称、传感器量程、保存路径等。
- 确保 `DATA_SAVE_DIR` 和 `NEW_DATA_SAVE_DIR` 目录可写。

### 运行
```bash
python main.py
```

### 停止
按 `Ctrl+C`，程序会关闭所有线程和 NI 任务。

---

## 数据保存格式

### 旧格式（`DATA_SAVE_DIR`）
```
saved_data/
└── {spec_name}/
    ├── OK/
    │   └── {barcode}/
    │       └── ch0.csv, ch1.csv, ...
    └── NG/
        └── {barcode}/
            └── ch0.csv, ch1.csv, ...
```
每个 CSV 包含两列：`time` 和对应通道的振动/电流值。

### 新格式（`NEW_DATA_SAVE_DIR`，可开关）
```
D:/DATA/
└── {year}/
    └── {yyyyMMdd}/
        ├── OK/
        │   └── {barcode}/
        │       └── {HHMM}/
        │           ├── forward/
        │           │   ├── forward_data.csv
        │           │   ├── forward_vibration_X.png
        │           │   ├── forward_vibration_Y.png
        │           │   ├── forward_vibration_Z.png
        │           │   ├── forward_current.png
        │           │   ├── forward_audio_X.wav
        │           │   ├── forward_audio_Y.wav
        │           │   └── forward_audio_Z.wav
        │           └── backward/
        │               └── (同上)
        └── NG/
            └── ...
```
每个分段（正转/反转）保存完整时间序列、各轴振动图、电流图以及三轴音频（WAV 格式，可用于声音分析）。

---

## 工作流程（自动模式）

1. **PLC 发送条码/规格/模式** 到指定寄存器。
2. **PLC 触发 `READY` 命令**（或数据就绪信号），PC 读取条码，加载模型，回复 `PC_STATUS_READY`。
3. **PLC 发送 `START` 命令**，PC 启动采集（延迟后开始记录）。
4. **PLC 发送 `FIRST_END`**，PC 记录第一段结束位置，暂停 WebSocket 推送。
5. **PLC 发送 `SECOND_START`**，PC 继续采集（时间连续），恢复推送。
6. **PLC 发送 `STOP`**，PC 停止采集，拼接两段数据，进行模型推理。
7. PC 将结果（1=OK, 2=NG）写入结果寄存器，并置位结果就绪标志，同时将状态置为 `PC_STATUS_COMPLETE`。
8. PLC 读取结果后复位命令，开始下一循环。

---

## 扩展与定制

- **添加新规格模型**：将训练好的 `.pth` 文件放入 `logs/models/`，命名为 `{规格名}.pth`，系统将自动加载。
- **调整采集延迟**：修改 `config.py` 中的 `START_DELAY`。
- **更换前端**：WebSocket 协议已定义好消息格式，可对接任何前端框架。

---

## 注意事项

- NI DAQ 设备名称需与 `config.py` 中的通道字符串一致（如 `cDAQ1Mod1/ai0:2`）。
- 确保 PLC 的寄存器地址与程序定义匹配。
- 采集任务会占用大量 CPU，建议在性能足够的工业 PC 上运行。
- 训练脚本 `train_from_saved.py` 需手动执行，不会在 `main.py` 中自动调用。

---

## 作者与许可

本项目为工业质检内部使用，如需二次开发请参考各模块注释。  
如有问题，请联系开发团队。