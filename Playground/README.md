# Playground — MCP 测试目录

这个目录本身没有代码，只有 `opencode.json`，里面配了两个远程 MCP：

| MCP 名 | 地址 | 源码目录 | 工具 |
| --- | --- | --- | --- |
| `pet-hospital` | http://127.0.0.1:8766/mcp | `E:\LLM\PetHospitalMCP` | `list_pets` |
| `anythingllm` | http://127.0.0.1:8765/mcp | `E:\LLM\AnythingLLMMCP` | `list_workspace_files` |

两个都是 **Streamable HTTP + 无状态**：`stateless_http=True` + `json_response=True`，
不需要 `initialize` 握手，也不保持 SSE 长连接，所以 2026-07-28 前后的两版
MCP 协议客户端都能直接连。

## 使用步骤

三个服务要先起来（每个一个终端窗口）：

```powershell
# 1. 宠物医院 REST 服务器
E:\LLM\PetHospitalServer\pethospital.exe

# 2. 宠物医院 MCP（不需要 Key）
cd E:\LLM\PetHospitalMCP
$env:PETHOSPITAL_BASE_URL = "http://127.0.0.1:8080"
.venv\Scripts\python.exe server.py

# 3. AnythingLLM MCP（需要 Key）
cd E:\LLM\AnythingLLMMCP
$env:ANYTHINGLLM_BASE_URL = "http://localhost:3001"
$env:ANYTHINGLLM_API_KEY = "你的API Key"
.venv\Scripts\python.exe server.py
```

然后用 opencode 打开 `E:\LLM\Playground` 这个目录，工具会读 `opencode.json`
自动连接上面两个 MCP。

## 自测（不经过 MCP 客户端，直接打 MCP 协议）

因为是无状态的，一次 POST 就能调工具，不用先握手：

```powershell
$b = @{jsonrpc="2.0"; id=1; method="tools/call";
       params=@{name="list_pets"; arguments=@{species="猫"; pageSize=2}}} | ConvertTo-Json -Depth 6

Invoke-WebRequest -Uri "http://127.0.0.1:8766/mcp" -Method Post `
  -ContentType "application/json" `
  -Headers @{Accept="application/json, text/event-stream"} `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($b)) -UseBasicParsing |
  Select-Object -ExpandProperty Content
```

返回的响应头里没有 `Mcp-Session-Id`、`Content-Type` 是 `application/json`，
就说明握手和长链接确实被去掉了。

## 上传文档到 AnythingLLM

浏览器打开 `E:\LLM\AnythingLLMWebPage\anythingllm-upload.html`，
填服务器地址和 API Key，选文件点「上传并嵌入」。它会自动取第一个工作区、
走 `POST /api/v1/document/upload`、然后轮询直到向量化嵌入完成。
