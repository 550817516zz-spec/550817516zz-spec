# xAgent

把 `Practice02/chat.py` 的单文件脚本，重构为「业务内核 + 多前端」的模块化 Agent 工程。

核心思想：**core 层不认识界面，界面层不认识模型**。两者之间只有一份事件协议（`core.agent.events`），
因此新增 Web / Desktop / Mobile 端不需要改动任何业务代码。

---

## 1. 目录结构

```
xAgent/
├── core/                    # 业务内核：不依赖任何 UI 框架
│   ├── agent/               # 业务编排层
│   │   ├── engine.py        #   Agent 引擎：ReAct 循环 + 工具调度
│   │   ├── events.py        #   事件协议（前端唯一的数据契约）
│   │   └── session.py       #   会话与消息历史
│   ├── tools/               # 能力层
│   │   ├── base.py          #   Tool 抽象 / @tool 装饰器 / JSON Schema 推导
│   │   ├── registry.py      #   工具注册表
│   │   └── builtin/         #   内置工具（时间、计算、文件、联网搜索）
│   ├── llm/                 # 基础设施层
│   │   ├── base.py          #   LLMClient 接口
│   │   └── openai_client.py #   OpenAI 兼容实现（DeepSeek / OpenAI / 网关）
│   ├── context/             # 上下文压缩、归档与检索
│   │   ├── manager.py       #   Token 监控与 70% 阈值控制
│   │   ├── archive.py       #   .agents/context/ JSONL 归档与 recallContext
│   │   ├── tokens.py        #   Token 估算与上下文窗口识别
│   │   └── prompt.py        #   上下文压缩专用 Prompt
│   ├── config/              # 配置层：config.ini + 环境变量覆盖
│   ├── models/              # 领域模型：Message / ToolCall / Role
│   ├── skills/              # Agent Skills 发现与按需加载
│   ├── mcp/                 # MCP Client（Streamable HTTP）
│   │   ├── config.py        #   .mcp.json 解析
│   │   ├── transport.py     #   后台事件循环中的连接与工具调用
│   │   ├── tools.py         #   把 MCP 工具包装成 Tool
│   │   └── manager.py       #   发现、注册、命名冲突与生命周期
│   ├── workspace.py         # 文件工具沙箱
│   ├── exceptions.py        # 统一异常体系
│   └── bootstrap.py         # 装配根：集中创建各组件
│
├── tui/                     # Textual 终端界面（前端层）
│   ├── app.py               #   App 外壳，只做装配与生命周期
│   ├── screens/chat_screen.py  # 对话主界面
│   ├── widgets/             #   可复用组件（消息块 / 消息流 / 输入框 / 状态栏）
│   └── styles.tcss          #   样式
│
├── web/                     # 预留：Web 前端
├── desktop/                 # 预留：桌面端
├── mobile/                  # 预留：移动端
│
├── tests/                   # 标准库 unittest，无需 pytest
├── main.py                  # 命令行入口
├── config.ini               # 本地配置（已被 .gitignore 忽略）
├── config.example.ini       # 配置模板
├── pyproject.toml
├── requirements.txt
└── architecture.mmd         # 架构图（Mermaid）
```

## 2. 分层规范

| 层次 | 目录 | 职责 | 允许依赖 |
| --- | --- | --- | --- |
| 前端层 | `tui/` `web/` `desktop/` `mobile/` | 渲染、输入、事件流消费 | 只依赖 `core` |
| 编排层 | `core/agent/` | 循环控制、事件派发、会话维护 | `core.tools` `core.llm` `core.models` |
| 能力层 | `core/tools/` | 工具定义、注册、执行 | `core.workspace` |
| 基础设施层 | `core/llm/` `core/config/` | 模型接入、配置装载 | `core.models` |
| 领域层 | `core/models/` | 数据结构定义 | 无 |

约束：

- `core` 不 import 任何界面库（textual / fastapi / PySide6 …）；
- 前端不直接调用模型或工具，只能消费 `AgentEvent`；
- 跨层通信通过 `core.bootstrap` 的装配函数完成，不在模块内部隐式创建依赖；
- 所有异常收敛到 `core.exceptions.XAgentError` 体系。

## 3. 事件协议

`AgentEngine.run()` 是一个异步生成器，按顺序产出事件：

| 事件 | 含义 |
| --- | --- |
| `UserMessageEvent` | 用户输入已接收 |
| `AssistantDeltaEvent` | 助手回复的增量文本（流式渲染） |
| `ToolCallEvent` | 模型发起工具调用 |
| `ToolResultEvent` | 工具执行结果（`ok` 表示成功与否） |
| `AssistantMessageEvent` | 助手完整回复 |
| `ContextStatusEvent` | 当前上下文占用、窗口大小与百分比 |
| `ContextWarningEvent` | 上下文达到 70% 阈值，需要执行 `/compact` |
| `CompactionStartedEvent` | 上下文压缩开始及归档进度 |
| `CompactionFinishedEvent` | 上下文压缩成功完成 |
| `ErrorEvent` | 执行错误（不会中断会话） |
| `DoneEvent` | 本轮结束 |

## 4. 快速开始

```bash
cd xAgent
pip install -r requirements.txt

# 复制配置模板并填写 API Key
copy config.example.ini config.ini      # Windows
# cp config.example.ini config.ini     # Linux / macOS

python main.py
```

也可以用环境变量覆盖敏感配置（优先级高于 `config.ini`）：

```bash
set XAGENT_API_KEY=sk-xxx
set XAGENT_MODEL=deepseek-chat
```

在 `config.ini` 的 `[search]` 段填写 `baidu_qianfan_api_key` 后，会额外注册 `web_search` 联网搜索工具
（调用百度千帆 AI 搜索接口）；未填写时该工具不会注册。

如果运行目录下存在 `.mcp.json`，xAgent 会在启动时自动连接其中配置的 MCP Server，
并把远端工具注册到同一个工具集合中。详见第 7 节。

常用参数：

```bash
python main.py --config path/to/config.ini   # 指定配置文件
python main.py --workspace .                  # 指定文件工具的工作区
python main.py --no-stream                    # 关闭流式输出
python main.py --list-tools                   # 打印可用工具后退出
```

界面内命令：`/help`、`/compact`、`/clear`、`/tools`、`/history`、`/doctor`；输入 `exit` / `quit` / `q` 退出。

## 5. 扩展一个工具

```python
from core.tools.base import tool

@tool("把文本转成大写")
def to_upper(text: str) -> str:
    """把输入文本转换为大写。

    Args:
        text: 需要转换的文本
    """
    return text.upper()
```

注册（通常在 `core/tools/builtin/` 中完成，或在 `bootstrap.py` 中注入）：

```python
registry.register(to_upper)
```

`@tool` 会自动从类型注解与 docstring 推导出 OpenAI 兼容的 JSON Schema，无需手写参数定义。

## 6. Agent Skills（技能动态加载）

在程序启动目录下创建 `.agents/skills/<skill-name>/SKILL.md`，即可注册一个 Skill：

```text
.agents/
└── skills/
    └── pdf/
        ├── SKILL.md
        └── references/
            └── forms.md
```

`SKILL.md` 必须以 YAML Frontmatter 开头，并包含 `name` 与 `description`：

```markdown
---
name: pdf
description: 读取、拆分与填写 PDF 表单时使用。
---

# PDF 处理

详细步骤写在这里，只有模型调用 `loadSkill` 时才会被加载。
```

启动时 xAgent 只读取 `name` 与 `description` 并注入系统提示词，不会把正文放进上下文。
模型需要完整说明时调用 `loadSkill`：

- `loadSkill(name="pdf")`：返回 `SKILL.md` 全文；
- `loadSkill(name="pdf", filename="references/forms.md")`：读取 Skill 目录内的附加文件。

`filename` 支持相对于 Skill 目录的路径、项目相对路径和绝对路径；只给文件名时会递归查找，
唯一匹配才返回，存在多个同名文件则返回候选路径。所有读取都被限制在该 Skill 目录内。

也可以让 Agent 直接创建 Skill。模型会调用 `createSkill`：

```text
createSkill(name="pdf-forms", skillContext="# PDF 表单\n\n处理 PDF 表单的步骤……")
```

该工具会：

- 把 `name` 规范为小写字母、数字和连字符组成的英文目录名（例如 `Pdf Forms` → `pdf-forms`）；
- 在 `.agents/skills/<name>/` 下创建 `SKILL.md`，自动生成符合规范的 YAML Frontmatter；
- 如果 `skillContext` 自带 Frontmatter，则保留其中的 `description`，并把 `name` 修正为规范名称；
- 目标 Skill 已存在时直接返回提示，不会覆盖原有内容；
- 创建成功后刷新当前会话的 Skill 清单，无需重启即可调用 `loadSkill` 使用。

需要 `references/`、`scripts/` 等附加文件时，模型会继续调用 `create_directory`、`create_file`
和 `edit_file_content` 等文件工具完成。

## 7. MCP Client（连接外部 MCP Server）

xAgent 启动时会读取**当前运行项目目录**（`Path.cwd()`，不是 xAgent 源码目录）下的
`.mcp.json`，通过 MCP Python SDK 连接 Streamable HTTP Server，调用 `list_tools()`
发现工具，并动态注册到现有的 `ToolRegistry` 中。

```json
{
  "mcpServers": {
    "Bazi-MCP": {
      "type": "streamable_http",
      "url": "https://mcp.api-inference.modelscope.net/c073dbc359844c/mcp"
    }
  }
}
```

支持的配置字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `type` | 否 | 固定为 `streamable_http`（兼容 `http` / `streamable-http`），默认即此值 |
| `url` | 是 | MCP Server 的 Streamable HTTP 端点，必须以 `http://` 或 `https://` 开头 |
| `headers` | 否 | 附加到请求中的 HTTP Header，例如鉴权 Token |
| `timeout` | 否 | 连接与单次工具调用超时秒数，默认 30 |
| `enabled` | 否 | 设为 `false` 可跳过该 Server |

工具注册规则：

- 默认保留远端工具名；如果与本地工具（如 `web_search`、`loadSkill`）或其他
  Server 的工具重名，则自动加服务器前缀，例如 `Bazi-MCP_getChineseCalendar`；
- 仍冲突时追加数字后缀；工具名会规范为 Function Calling 允许的
  `[A-Za-z0-9_-]` 字符并限制在 64 字符内；
- 内部维护两组映射：`暴露名 -> (Server, 远端工具名)` 与
  `Server -> (远端工具名 -> 暴露名)`，LLM 发起调用时据此转发参数。

调用链路与本地工具完全一致：

```text
LLM function call -> AgentEngine._execute_tool -> MCPTool.execute
                  -> MCPConnection.call_tool -> MCP Server -> 文本/结构化结果
```

工具返回的文本内容、图片/资源摘要、`structuredContent` 结构化数据都会被整理成
模型易读的文本；`isError` 结果和连接/调用异常会作为失败的工具结果返回给 LLM。

某个 Server 配置错误或连接失败时，只会跳过该 Server 并输出明确的 `[MCP]` 错误，
其他 MCP 工具与本地工具仍可正常使用。可用环境变量：

```bash
set XAGENT_MCP_CONFIG=path/to/.mcp.json   # 指定其他配置文件
set XAGENT_MCP_DISABLED=1                 # 临时关闭 MCP 加载
```

## 8. 上下文压缩与历史检索

xAgent 会在每次模型响应后检查上下文占用。统计范围包括 System Prompt、用户消息、
对话历史、工具调用参数与工具返回结果：

- 优先使用模型 API 返回的 `usage`（流式请求会通过 `stream_options.include_usage` 获取）；
- 无法获取 usage 时，用本地规则估算（CJK 字符约 1 token/字，其他字符约 4 字符/token）；
- 上下文窗口优先读取 `[llm].context_window`，其次识别常见模型，无法识别时按 128k 处理，
  并在界面上标记“默认”。

顶部信息条会醒目显示：

```text
上下文 23.4k / 128k（18.3%）· API
```

占用达到窗口的 **70%** 后，会显示警告并暂停接受新的普通提示词。此时执行 `/compact`：

1. 先把完整原始上下文写入 `.agents/context/<编号>.jsonl`
   （例如 `20261022-153000.jsonl`），保留角色、正文、工具调用参数、工具结果和顺序；
2. 只调用 LLM 生成约 5,000 Tokens 的 Markdown 工作摘要，不执行任何其他工具；
3. 保留 System Prompt 与工具定义，用摘要替换原有历史，并在摘要末尾写入归档说明；
4. 压缩成功后解除输入限制，并弹出双栏对照面板：左侧为压缩前原文，右侧为压缩后摘要，
   两栏都可以用鼠标滚轮滚动，点击“关闭”按钮退出；
5. 失败则保留原上下文，可以重新执行 `/compact`。

压缩过程会写入 `.agents/logs/compact.log`，记录开始、归档、摘要生成、成功或失败等信息。

归档文件内容示例（一行一条消息）：

```json
{"index":2,"role":"assistant","content":"","tool_calls":[{"id":"call_1","type":"function","function":{"name":"get_file_content","arguments":"{\"file_path\": \"a.txt\"}"}}]}
{"index":3,"role":"tool","content":"文件内容……","tool_call_id":"call_1","name":"get_file_content"}
```

压缩后如果摘要缺少细节，模型可以调用普通工具 `recallContext`：

```text
recallContext(text="关键词")              # 检索全部归档
recallContext(text="关键词", id="20261022-153000")  # 只检索指定归档
```

`recallContext` 使用本地 JSONL 全文关键词匹配，返回匹配片段、归档编号和消息位置，
并限制返回长度，避免检索结果再次占满上下文。

## 9. 扩展一个新前端

以 Web 为例，只需在 `web/` 中消费同一套事件流：

```python
from core.bootstrap import build_engine

engine = build_engine()

async def chat_stream(user_text: str):
    async for event in engine.run(user_text):
        yield event
```

前端不需要知道模型是谁、不需要知道工具怎么执行、会话状态由 `core.agent.session.Session` 统一维护。

## 10. 安全约束

- 文件类工具全部受 `core.workspace.Workspace` 约束，只能访问工作区根目录内的路径；
- `loadSkill` 只允许读取当前 Skill 目录内的文件，路径穿越与越界绝对路径都会被拒绝；
- `config.ini` 已被 `.gitignore` 忽略，模型密钥建议用环境变量 `XAGENT_API_KEY` 提供；
- `[search].baidu_qianfan_api_key` 同样属于敏感信息，仅在需要联网搜索时填写；
- `.mcp.json` 中的 `headers` 可能包含 Token，建议不要提交到版本库；
- `.agents/context/` 保存了完整的原始对话（包括工具结果），可能含有敏感信息，建议按需清理；
- `.agents/logs/compact.log` 只记录压缩过程元信息，不记录完整原文，但归档文件仍可能包含敏感内容；
- `calculate` 工具使用 AST 白名单解析，只允许四则运算，不执行任意代码。

## 11. 测试

```bash
python -m unittest discover -s tests -t .
```

覆盖内容：工具 Schema 推导、注册表、工作区沙箱越界拦截、引擎的工具调用回路与异常兜底、
Agent Skills 发现/创建/按需加载/路径越界拦截、MCP 配置解析/工具命名/结果格式化/失败隔离、
上下文 Token 估算/阈值控制/归档保存/全文检索/压缩替换、TUI 启动与渲染冒烟。
