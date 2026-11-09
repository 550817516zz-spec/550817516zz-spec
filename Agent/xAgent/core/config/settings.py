"""配置加载：config.ini + 环境变量覆盖 + 缺省参数。

所有可调参数都集中在 :class:`Settings` 中。配置文件只写需要改动的项，
未填写的项使用这里定义的默认值，因此升级后不会因为旧配置文件缺字段而报错。
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

from core.exceptions import ConfigurationError

ENV_CONFIG_PATH = "XAGENT_CONFIG"
ENV_API_KEY = "XAGENT_API_KEY"
ENV_BASE_URL = "XAGENT_BASE_URL"
ENV_MODEL = "XAGENT_MODEL"

CONFIG_FILENAMES = ("config.ini", "xagent.ini")

DEFAULT_SYSTEM_PROMPT = (
    "你是一个命令行助手，具备调用工具的能力。"
    "需要操作文件或系统信息时优先使用工具，工具失败时请根据错误信息调整后重试。"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class LLMSettings:
    """模型服务连接参数。"""

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout: float = 120.0
    max_iterations: int = 8
    stream: bool = True
    context_window: int | None = None


@dataclass(slots=True)
class WorkspaceSettings:
    """文件工具可访问的目录范围。"""

    root: Path = field(default_factory=Path.cwd)
    read_only: bool = False


@dataclass(slots=True)
class SearchSettings:
    """联网搜索服务参数。"""

    baidu_qianfan_api_key: str = ""
    endpoint: str = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    timeout: float = 20.0
    max_query_length: int = 72
    max_results: int = 50
    max_content_per_item: int = 300
    max_total_length: int = 6000


@dataclass(slots=True)
class FileToolSettings:
    """文件读取工具的容量参数。"""

    max_content_length: int = 10_000
    text_sniff_size: int = 8192


@dataclass(slots=True)
class BrowserSettings:
    """agent-browser CLI 参数。"""

    executable_path: str = "tool/agent-browse/agent-browser-win32-x64.exe"
    screenshot_dir: str = ""
    timeout: float = 120.0


@dataclass(slots=True)
class ContextSettings:
    """上下文估算、压缩与归档参数。"""

    default_window: int = 128_000
    compact_threshold: float = 0.70
    compact_target_tokens: int = 5_000
    message_overhead: int = 4
    archive_subdir: str = ".agents/context"
    max_hits: int = 20
    max_total_chars: int = 6000
    snippet_chars: int = 300
    log_subdir: str = ".agents/logs"
    log_filename: str = "compact.log"


@dataclass(slots=True)
class SessionSettings:
    """会话持久化与 AGENTS.md 注入参数。"""

    directory: str = ".agents/sessions"
    export_dir: str = ".agents/exports"
    auto_save: bool = True
    event_log: bool = True
    list_limit: int = 30
    title_max_chars: int = 48
    agents_md_filename: str = "AGENTS.md"
    agents_md_max_chars: int = 20_000


@dataclass(slots=True)
class MCPSettings:
    """MCP 客户端参数。"""

    config_filename: str = ".mcp.json"
    default_timeout: float = 30.0
    auto_load: bool = True
    async_load: bool = True


@dataclass(slots=True)
class UISettings:
    """终端界面展示参数。"""

    tool_result_limit: int = 800
    tool_card_max_preview: int = 600
    session_list_limit: int = 30
    sidebar_width: int = 36
    suggest_limit: int = 8
    theme: str = ""


@dataclass(slots=True)
class Settings:
    """应用全局配置。"""

    llm: LLMSettings = field(default_factory=LLMSettings)
    workspace: WorkspaceSettings = field(default_factory=WorkspaceSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    file_tools: FileToolSettings = field(default_factory=FileToolSettings)
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    sessions: SessionSettings = field(default_factory=SessionSettings)
    mcp: MCPSettings = field(default_factory=MCPSettings)
    ui: UISettings = field(default_factory=UISettings)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    agents_md_enabled: bool = True
    config_path: Path | None = None


DEFAULT_CONFIG_CONTENT = """\
# xAgent 配置文件
# 该文件由程序在首次启动时自动生成。请修改下面标记为 mock 的参数，
# 尤其是 [llm] 段的 base_url / api_key / model，保存后重新启动 xAgent 才能正常工作。
# 未填写的配置项会自动使用程序内置默认值。

[llm]
base_url = http://127.0.0.1:11434/v1
api_key = mock-api-key-please-edit
model = mock-model-please-edit
temperature = 0.7
timeout = 120
max_iterations = 8
stream = true
# 模型上下文窗口（tokens）。留空时自动识别常见模型；无法识别则使用 [context].default_window。
context_window =
# max_tokens = 4096

[workspace]
root = .
read_only = false

[agent]
system_prompt = 你是一个命令行助手，具备调用工具的能力。需要操作文件或系统信息时优先使用工具，工具失败时请根据错误信息调整后重试。
# 是否在会话首次加载时注入当前目录的 AGENTS.md
agents_md = true

[search]
# 百度千帆应用的 API Key，用于联网搜索工具
baidu_qianfan_api_key = mock-baidu-qianfan-key-please-edit
endpoint = https://qianfan.baidubce.com/v2/ai_search/web_search
timeout = 20
max_query_length = 72
max_results = 50
max_content_per_item = 300
max_total_length = 6000

[file_tools]
max_content_length = 10000
text_sniff_size = 8192

[browser]
# 相对于工作区根目录的可执行文件路径
executable_path = tool/agent-browse/agent-browser-win32-x64.exe
# 留空时使用可执行文件所在目录
screenshot_dir =
timeout = 120

[context]
default_window = 128000
compact_threshold = 0.70
compact_target_tokens = 5000
message_overhead = 4
archive_subdir = .agents/context
max_hits = 20
max_total_chars = 6000
snippet_chars = 300
log_subdir = .agents/logs
log_filename = compact.log

[sessions]
directory = .agents/sessions
export_dir = .agents/exports
auto_save = true
event_log = true
list_limit = 30
title_max_chars = 48
agents_md_filename = AGENTS.md
agents_md_max_chars = 20000

[mcp]
config_filename = .mcp.json
default_timeout = 30
auto_load = true
# 先进入 TUI，再在后台异步连接 MCP Server 并刷新侧栏
async_load = true

[ui]
tool_result_limit = 800
tool_card_max_preview = 600
session_list_limit = 30
sidebar_width = 36
suggest_limit = 8
# 留空使用 Textual 默认主题；可填写 textual-dark / textual-light 等
theme =
"""


def resolve_config_path(config_path: str | os.PathLike[str] | None = None) -> Path | None:
    """按 显式路径 > 环境变量 > 当前目录 > 项目目录 的顺序定位配置文件。"""
    if config_path:
        candidate = Path(config_path).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        raise ConfigurationError(f"配置文件不存在：{candidate}")

    env_path = os.environ.get(ENV_CONFIG_PATH)
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        raise ConfigurationError(f"环境变量 {ENV_CONFIG_PATH} 指向的配置文件不存在：{candidate}")

    for directory in (Path.cwd(), PROJECT_ROOT):
        for filename in CONFIG_FILENAMES:
            candidate = directory / filename
            if candidate.is_file():
                return candidate.resolve()
    return None


def ensure_default_config(
    base_dir: str | os.PathLike[str] | None = None,
    *,
    filename: str = "config.ini",
) -> tuple[Path, bool]:
    """确保指定目录存在 config.ini。

    返回 ``(路径, 是否本次新建)``。新建的文件包含完整段落和 mock 配置，
    调用方应提示用户修改后重新启动。
    """
    directory = Path(base_dir or Path.cwd()).expanduser().resolve()
    target = directory / filename
    if target.is_file():
        return target, False
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target.write_text(DEFAULT_CONFIG_CONTENT, encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"无法创建配置文件 {target}：{exc}") from exc
    return target, True


def _get(section: dict[str, str], key: str, default: str = "") -> str:
    value = section.get(key, default)
    return value.strip() if isinstance(value, str) else default


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _to_int(value: str | None, default: int | None) -> int | None:
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ConfigurationError(f"非法整数配置：{value}") from exc


def _to_float(value: str | None, default: float) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise ConfigurationError(f"非法浮点数配置：{value}") from exc


def load_settings(config_path: str | os.PathLike[str] | None = None) -> Settings:
    """加载配置；未填写的项回退到内置默认值。"""
    resolved = resolve_config_path(config_path)
    parser = configparser.ConfigParser()
    if resolved is not None:
        parser.read(resolved, encoding="utf-8")

    llm_raw = dict(parser["llm"]) if parser.has_section("llm") else {}
    agent_raw = dict(parser["agent"]) if parser.has_section("agent") else {}
    workspace_raw = dict(parser["workspace"]) if parser.has_section("workspace") else {}
    search_raw = dict(parser["search"]) if parser.has_section("search") else {}
    file_raw = dict(parser["file_tools"]) if parser.has_section("file_tools") else {}
    browser_raw = dict(parser["browser"]) if parser.has_section("browser") else {}
    context_raw = dict(parser["context"]) if parser.has_section("context") else {}
    sessions_raw = dict(parser["sessions"]) if parser.has_section("sessions") else {}
    mcp_raw = dict(parser["mcp"]) if parser.has_section("mcp") else {}
    ui_raw = dict(parser["ui"]) if parser.has_section("ui") else {}

    llm = LLMSettings(
        base_url=os.environ.get(ENV_BASE_URL) or _get(llm_raw, "base_url"),
        api_key=os.environ.get(ENV_API_KEY) or _get(llm_raw, "api_key"),
        model=os.environ.get(ENV_MODEL) or _get(llm_raw, "model"),
        temperature=_to_float(llm_raw.get("temperature"), 0.7),
        max_tokens=_to_int(llm_raw.get("max_tokens"), None),
        timeout=_to_float(llm_raw.get("timeout"), 120.0),
        max_iterations=_to_int(llm_raw.get("max_iterations"), 8) or 8,
        stream=_to_bool(llm_raw.get("stream"), True),
        context_window=_to_int(llm_raw.get("context_window"), None),
    )

    if not llm.base_url:
        raise ConfigurationError("缺少 base_url 配置，请在 config.ini 的 [llm] 段填写。")
    if not llm.model:
        raise ConfigurationError("缺少 model 配置，请在 config.ini 的 [llm] 段填写。")
    if not llm.api_key:
        raise ConfigurationError("缺少 api_key 配置，请填写配置项或设置环境变量 XAGENT_API_KEY。")

    root_value = _get(workspace_raw, "root")
    root = Path(root_value).expanduser().resolve() if root_value else Path.cwd().resolve()

    search = SearchSettings(
        baidu_qianfan_api_key=_get(search_raw, "baidu_qianfan_api_key"),
        endpoint=_get(
            search_raw,
            "endpoint",
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
        ),
        timeout=_to_float(search_raw.get("timeout"), 20.0),
        max_query_length=_to_int(search_raw.get("max_query_length"), 72) or 72,
        max_results=_to_int(search_raw.get("max_results"), 50) or 50,
        max_content_per_item=_to_int(search_raw.get("max_content_per_item"), 300) or 300,
        max_total_length=_to_int(search_raw.get("max_total_length"), 6000) or 6000,
    )

    file_tools = FileToolSettings(
        max_content_length=_to_int(file_raw.get("max_content_length"), 10_000) or 10_000,
        text_sniff_size=_to_int(file_raw.get("text_sniff_size"), 8192) or 8192,
    )

    browser = BrowserSettings(
        executable_path=_get(
            browser_raw,
            "executable_path",
            "tool/agent-browse/agent-browser-win32-x64.exe",
        ),
        screenshot_dir=_get(browser_raw, "screenshot_dir"),
        timeout=_to_float(browser_raw.get("timeout"), 120.0),
    )

    context = ContextSettings(
        default_window=_to_int(context_raw.get("default_window"), 128_000) or 128_000,
        compact_threshold=_to_float(context_raw.get("compact_threshold"), 0.70),
        compact_target_tokens=_to_int(context_raw.get("compact_target_tokens"), 5_000) or 5_000,
        message_overhead=_to_int(context_raw.get("message_overhead"), 4) or 4,
        archive_subdir=_get(context_raw, "archive_subdir", ".agents/context") or ".agents/context",
        max_hits=_to_int(context_raw.get("max_hits"), 20) or 20,
        max_total_chars=_to_int(context_raw.get("max_total_chars"), 6000) or 6000,
        snippet_chars=_to_int(context_raw.get("snippet_chars"), 300) or 300,
        log_subdir=_get(context_raw, "log_subdir", ".agents/logs") or ".agents/logs",
        log_filename=_get(context_raw, "log_filename", "compact.log") or "compact.log",
    )

    sessions = SessionSettings(
        directory=_get(sessions_raw, "directory", ".agents/sessions") or ".agents/sessions",
        export_dir=_get(sessions_raw, "export_dir", ".agents/exports") or ".agents/exports",
        auto_save=_to_bool(sessions_raw.get("auto_save"), True),
        event_log=_to_bool(sessions_raw.get("event_log"), True),
        list_limit=_to_int(sessions_raw.get("list_limit"), 30) or 30,
        title_max_chars=_to_int(sessions_raw.get("title_max_chars"), 48) or 48,
        agents_md_filename=_get(sessions_raw, "agents_md_filename", "AGENTS.md") or "AGENTS.md",
        agents_md_max_chars=_to_int(sessions_raw.get("agents_md_max_chars"), 20_000) or 20_000,
    )

    mcp = MCPSettings(
        config_filename=_get(mcp_raw, "config_filename", ".mcp.json") or ".mcp.json",
        default_timeout=_to_float(mcp_raw.get("default_timeout"), 30.0),
        auto_load=_to_bool(mcp_raw.get("auto_load"), True),
        async_load=_to_bool(mcp_raw.get("async_load"), True),
    )

    ui = UISettings(
        tool_result_limit=_to_int(ui_raw.get("tool_result_limit"), 800) or 800,
        tool_card_max_preview=_to_int(ui_raw.get("tool_card_max_preview"), 600) or 600,
        session_list_limit=_to_int(ui_raw.get("session_list_limit"), 30) or 30,
        sidebar_width=_to_int(ui_raw.get("sidebar_width"), 36) or 36,
        suggest_limit=_to_int(ui_raw.get("suggest_limit"), 8) or 8,
        theme=_get(ui_raw, "theme"),
    )

    settings = Settings(
        llm=llm,
        workspace=WorkspaceSettings(
            root=root,
            read_only=_to_bool(workspace_raw.get("read_only"), False),
        ),
        search=search,
        file_tools=file_tools,
        browser=browser,
        context=context,
        sessions=sessions,
        mcp=mcp,
        ui=ui,
        system_prompt=_get(agent_raw, "system_prompt") or DEFAULT_SYSTEM_PROMPT,
        agents_md_enabled=_to_bool(agent_raw.get("agents_md"), True),
        config_path=resolved,
    )
    return settings


__all__ = [
    "BrowserSettings",
    "CONFIG_FILENAMES",
    "ContextSettings",
    "DEFAULT_CONFIG_CONTENT",
    "DEFAULT_SYSTEM_PROMPT",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "ENV_CONFIG_PATH",
    "ENV_MODEL",
    "FileToolSettings",
    "LLMSettings",
    "MCPSettings",
    "PROJECT_ROOT",
    "SearchSettings",
    "SessionSettings",
    "Settings",
    "UISettings",
    "WorkspaceSettings",
    "ensure_default_config",
    "load_settings",
    "resolve_config_path",
]
