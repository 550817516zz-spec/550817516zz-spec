# AnythingLLM MCP Server（MVP）

只做一件事：把「提取 AnythingLLM 第一个工作区里的文件信息」包装成 MCP 工具
`list_workspace_files`，用 Streamable HTTP 暴露，同时兼容 2026-07-28 前后两版
MCP 协议（无 initialize 握手、无 SSE 长连接）。

## 1. 安装依赖

```powershell
cd E:\LLM\AnythingLLMMCP
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. 启动

先确认 AnythingLLM 桌面客户端已启动（默认 http://localhost:3001），
然后：

```powershell
cd E:\LLM\AnythingLLMMCP
$env:ANYTHINGLLM_BASE_URL = "http://localhost:3001"
$env:ANYTHINGLLM_API_KEY = "你的API Key"
python server.py
```

服务监听 `http://127.0.0.1:8765/mcp`，这个终端窗口要保持开启。

验证端口：

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 8765 -InformationLevel Quiet
```

停止：在运行 `python server.py` 的窗口按 `Ctrl+C`；或在别处
`Stop-Process -Id <PID> -Force`（先用 `Get-NetTCPConnection -LocalPort 8765` 查 PID）。

## 3. MCP 配置

配置在 `E:\LLM\Playground\opencode.json`，两个 MCP（宠物医院 + 本项目）
都已写好。把 `Playground` 目录作为工作区打开，工具会自动连接。

## 4. 工具说明

`list_workspace_files()` 无参数。走两步 API：

1. `GET /api/v1/workspaces` → 取 `workspaces[0]`（第一个工作区）
2. `GET /api/v1/workspace/{slug}` → 读 `workspace.documents`

返回工作区名/slug、文件数，以及每个文档的 `title` / `docpath` /
`chunkCount` / `token_count_estimate`。**不返回正文**，避免撑爆上下文。

## 5. 排查

- 连不上：AnythingLLM 客户端是否在跑（3001 端口）
- 401/403：`ANYTHINGLLM_API_KEY` 是否填对
- 返回 `fileCount: 0`：第一个工作区里确实还没上传文档，用
  `E:\LLM\AnythingLLMWebPage\anythingllm-upload.html` 上传一个再试
