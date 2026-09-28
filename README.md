# MCP 课程实践项目

三次课程作业的代码集合。核心思路是**让 LLM 客户端通过 MCP 协议操作本地系统**：底层是普通的
REST 服务，上层包一层 MCP Server，把内部能力暴露成工具给 AI 调用。

```text
                 ┌──────────────────┐
   AI / 客户端 ──▶│  MCP 工具层      │  (Python, mcp>=2.0.0)
                 │  AnythingLLMMCP   │──▶ AnythingLLM 桌面端 :3001
                 │  PetHospitalMCP   │──▶ PetHospitalServer  :8080 (REST)
                 └──────────────────┘

   浏览器 ────────▶ AnythingLLMWebPage ──▶ AnythingLLM 桌面端 :3001
                    （上传文档 / 触发嵌入）
```

## 项目一览

| 目录 | 技术栈 | 作用 | 默认端口 |
| --- | --- | --- | --- |
| [`PetHospitalServer/`](PetHospitalServer/) | Go 标准库 | 宠物医院管理系统：REST API + 内嵌网页界面 + 单文件数据库 | `127.0.0.1:8080` |
| [`PetHospitalMCP/`](PetHospitalMCP/) | Python + `mcp` | 把宠物医院接口包装成 MCP 工具 `list_pets` | `127.0.0.1:8766` |
| [`AnythingLLMMCP/`](AnythingLLMMCP/) | Python + `mcp` | 把 AnythingLLM 文档列表包装成 MCP 工具 `list_workspace_files` | `127.0.0.1:8765` |
| [`AnythingLLMWebPage/`](AnythingLLMWebPage/) | 原生 HTML/JS | 单文件网页，向 AnythingLLM 上传文档并触发向量化嵌入 | — |

---

## 1. PetHospitalServer

本地宠物医院管理系统。**只用 Go 标准库**，无任何第三方依赖，`go build` 即可，
不需要联网拉包。

- 浏览器打开 `http://127.0.0.1:8080/` 就是**网页操作界面**（HTML/CSS/JS 已内嵌进可执行文件）
- 29 个 REST 接口：查询 / 新增 / 编辑 / 删除 / 批量 / 导出 / 统计
- **无鉴权、无登录**，只监听本机，**请勿直接暴露到公网**
- 单文件数据库 `data/pet.db`：追加写日志（append-only）+ CRC32 校验 + 内存索引，
  自动压实（compaction），崩溃安全（临时文件 + `rename` 原子替换 + `fsync`），
  断电半条记录会被自动检测并截断修复
- 备份 = 直接复制 `data/pet.db` 一个文件

> **本仓库当前只包含该项目的文档（`README.md`、`README-Windows.md`、`LICENSE`）
> 与测试数据库 `data/pet.db`，不含 Go 源码和 `pethospital.exe`**（可执行文件被
> `.gitignore` 排除）。完整说明见 [PetHospitalServer/README.md](PetHospitalServer/README.md)。

## 2. PetHospitalMCP

把宠物医院的档案查询接口包装成 MCP 工具，供 AI 调用。

```powershell
cd PetHospitalMCP
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

$env:PETHOSPITAL_BASE_URL = "http://127.0.0.1:8080"   # 指向 PetHospitalServer
python server.py
```

**工具 `list_pets()`** 支持按名字 / 种类 / 状态 / 医生 / 疾病 / 主人过滤，
可按 `id`、`name`、`totalCost`、`visitCount` 排序，并带分页。
返回结果只保留 13 个列表字段，丢弃 `records`、`charges` 等大字段以节省 token。

## 3. AnythingLLMMCP

把 AnythingLLM 第一个工作区里的文件信息提取成一个 MCP 工具。

```powershell
cd AnythingLLMMCP
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

$env:ANYTHINGLLM_BASE_URL = "http://localhost:3001"   # AnythingLLM 桌面客户端
$env:ANYTHINGLLM_API_KEY   = "你的 API Key"
python server.py
```

**工具 `list_workspace_files()`** 无参数，走两步 API：
`GET /api/v1/workspaces` 取第一个工作区 → `GET /api/v1/workspace/{slug}` 读文档列表。
只返回文件名、路径、分块数、token 估算等元数据，**不返回正文**，避免撑爆上下文。

## 4. AnythingLLMWebPage

单文件网页工具，用来给 AnythingLLM **喂数据**——而上面三个项目是来读数据的。

直接用浏览器打开 `anythingllm-upload.html` 即可，无需服务器、无需构建、无第三方依赖：

1. 填服务器地址（默认 `http://localhost:3001`）和 API Key
2. 选择文件，点「上传并嵌入」
3. 页面会自动取第一个工作区，调用 `/api/v1/document/upload` 上传，
   然后每 3 秒轮询 `/api/v1/workspace/{slug}` 直到文档出现，最长等 60 秒

API Key 存在浏览器 `localStorage`（键名 `allm_key`），刷新页面不用重输，
页面底部有「清除 Key」链接可删除。**密钥不会写入任何文件。**

> 上一节排错里的 `fileCount: 0` 就是先用这个页面传一个文档解决的。

---

## MCP 配置

两个 MCP Server 都以 Streamable HTTP 暴露，需在客户端配置里注册：

```json
{
  "mcp": {
    "pet-hospital":     { "type": "local", "command": ["python", "server.py"], "cwd": "./PetHospitalMCP" },
    "anythingllm-files":{ "type": "local", "command": ["python", "server.py"], "cwd": "./AnythingLLMMCP" }
  }
}
```

两个服务启动时都使用 `stateless_http` + `json_response`：每次请求独立完成，
**不需要 `initialize` 握手、不保持 SSE 长连接**，同时兼容 2026-07-28 前后的两版 MCP 协议。

## 快速排错

| 现象 | 原因 / 处理 |
| --- | --- |
| MCP 连不上 | 先确认后端在跑：PetHospital `8080`、AnythingLLM `3001` |
| 401 / 403 | `ANYTHINGLLM_API_KEY` 是否填对 |
| 返回 `fileCount: 0` | 第一个工作区确实还没上传文档，先传一个再试 |
| 端口被占用 | 改 `server.py` 里的 `port` 参数，或查 PID 后 `Stop-Process` |
| 中文乱码 | PowerShell 里执行 `chcp 65001` |

## 许可

[`PetHospitalServer/`](PetHospitalServer/) 采用 MIT 许可证，见 [LICENSE](PetHospitalServer/LICENSE)。

## 约定

仓库不提交虚拟环境、可执行文件、压缩包与日志。相关规则见 [`.gitignore`](.gitignore)。
