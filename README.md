# Yanpu 振动噪声检测（PLC + 前端 + 模型推理）

本项目实现了完整最小闭环：

1. 前端点击按钮发送 PLC 指令  
2. 检测完成后读取固定路径 Excel/CSV 振动数据  
3. 数据处理后送入训练好的模型进行测试  
4. 前端显示振动波形与 OK/NG 结果

## 新增运行模块

- `app/plc_client.py`：PLC 通信（`mock` / `tcp`）  
- `app/inference_service.py`：读取 Excel/CSV + 预处理 + 模型推理  
- `app/service.py`：统一检测流程编排  
- `app/api.py`：FastAPI 后端接口  
- `app/desktop_app.py`：Tkinter 桌面前端（可打包 exe）  
- `run_backend.py`：后端启动入口  
- `run_frontend.py`：前端启动入口

## 环境变量配置

可通过环境变量配置运行参数（未设置则使用默认值）：

- `YANPU_MODEL_PATH`：模型路径，默认 `logs/best_model.pth`
- `YANPU_EXCEL_PATH`：检测文件路径，默认 `data/latest.xlsx`
- `YANPU_BACKEND_HOST`：后端地址，默认 `127.0.0.1`
- `YANPU_BACKEND_PORT`：后端端口，默认 `8000`
- `YANPU_BACKEND_REQUEST_TIMEOUT_SEC`：前端请求后端超时秒数，默认 `30`
- `YANPU_PLC_MODE`：`mock` 或 `tcp`，默认 `mock`
- `YANPU_PLC_HOST`：PLC TCP 地址，默认 `127.0.0.1`
- `YANPU_PLC_PORT`：PLC TCP 端口，默认 `5020`
- `YANPU_PLC_TIMEOUT_SEC`：PLC 超时，默认 `2.0`
- `YANPU_PLC_READ_RESPONSE`：是否读取响应，`1`/`0`

## 启动方式

### 1) 启动后端

```bash
python run_backend.py
```

后端接口：

- `GET /health`
- `POST /detect`

请求示例：

```json
{
  "command": "START_DETECT",
  "excel_path": "data/latest.xlsx"
}
```

### 2) 启动前端

```bash
python run_frontend.py
```

前端包含：

- 发送指令并检测按钮
- 状态展示（进行中/成功/失败）
- OK/NG 与置信度展示
- 振动波形展示（time/ax/ay/az）

## 打包为 exe（示例）

```bash
pyinstaller --noconfirm --onefile --windowed --name yanpu_frontend run_frontend.py
```

后端可单独打包或以 Python 服务方式部署。

## 异常处理

后端统一返回错误码：

- `PLC_ERROR`：PLC 发送失败/超时
- `INFERENCE_ERROR`：模型加载失败、文件不存在、格式错误、数据清洗后为空
