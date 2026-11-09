"""`.mcp.json` 配置解析。

只实现 Streamable HTTP 传输；配置文件沿用 MCP 生态中常见的
``{"mcpServers": {...}}`` 结构：

.. code-block:: json

    {
      "mcpServers": {
        "example": {
          "type": "streamable_http",
          "url": "https://example.com/mcp",
          "headers": {"Authorization": "Bearer ..."},
          "timeout": 30
        }
      }
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.exceptions import MCPConfigError

MCP_CONFIG_FILENAME = ".mcp.json"
ENV_MCP_CONFIG = "XAGENT_MCP_CONFIG"
ENV_MCP_DISABLED = "XAGENT_MCP_DISABLED"
DEFAULT_TIMEOUT = 30.0

_STREAMABLE_HTTP_TYPES = frozenset(
    {
        "streamable_http",
        "streamablehttp",
        "http",
        "https",
    }
)


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """一个 MCP Server 的连接参数。"""

    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = DEFAULT_TIMEOUT
    server_type: str = "streamable_http"


def mcp_disabled() -> bool:
    """是否通过环境变量显式关闭 MCP 加载。"""
    value = os.environ.get(ENV_MCP_DISABLED, "")
    return value.strip().lower() in ("1", "true", "yes", "on")


def resolve_mcp_config_path(
    project_root: Path | str | None = None,
    config_path: Path | str | None = None,
) -> Path:
    """定位 MCP 配置文件。

    优先级：显式参数 > ``XAGENT_MCP_CONFIG`` > 项目目录下的 ``.mcp.json``。
    项目目录默认是当前工作目录（运行 xAgent 的项目，而不是源代码目录）。
    """
    if config_path:
        return Path(config_path).expanduser().resolve()

    env_path = os.environ.get(ENV_MCP_CONFIG)
    if env_path:
        return Path(env_path).expanduser().resolve()

    root = Path(project_root or Path.cwd()).expanduser()
    return (root / MCP_CONFIG_FILENAME).resolve()


def _normalize_type(value: Any) -> str:
    raw = str(value or "streamable_http").strip().lower().replace("-", "_")
    return raw


def _parse_timeout(value: Any, server_name: str) -> float:
    if value is None or value == "":
        return DEFAULT_TIMEOUT
    if isinstance(value, bool):
        raise MCPConfigError(f"MCP Server「{server_name}」的 timeout 必须是正数。")
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise MCPConfigError(f"MCP Server「{server_name}」的 timeout 必须是正数。") from exc
    if timeout <= 0:
        raise MCPConfigError(f"MCP Server「{server_name}」的 timeout 必须大于 0。")
    return timeout


def _parse_headers(value: Any, server_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MCPConfigError(f"MCP Server「{server_name}」的 headers 必须是对象。")
    headers: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise MCPConfigError(
                f"MCP Server「{server_name}」的 headers 键和值都必须是字符串。"
            )
        headers[key] = item
    return headers


def _parse_server(name: str, payload: Any) -> MCPServerConfig:
    if not isinstance(payload, dict):
        raise MCPConfigError(f"MCP Server「{name}」的配置必须是对象。")

    server_type = _normalize_type(payload.get("type") or payload.get("transport"))
    if server_type not in _STREAMABLE_HTTP_TYPES:
        raise MCPConfigError(
            f"MCP Server「{name}」使用不支持的传输类型「{server_type}」。"
            "当前仅支持 Streamable HTTP（type=streamable_http）。"
        )

    url = str(payload.get("url") or payload.get("serverUrl") or "").strip()
    if not url:
        raise MCPConfigError(f"MCP Server「{name}」缺少 url 配置。")
    if not url.lower().startswith(("http://", "https://")):
        raise MCPConfigError(
            f"MCP Server「{name}」的 url 必须以 http:// 或 https:// 开头：{url}"
        )

    return MCPServerConfig(
        name=name,
        url=url,
        headers=_parse_headers(payload.get("headers"), name),
        timeout=_parse_timeout(payload.get("timeout"), name),
        server_type="streamable_http",
    )


def load_mcp_servers(
    path: Path | str,
) -> tuple[list[MCPServerConfig], list[str]]:
    """读取配置文件。

    返回 ``(有效配置列表, 错误信息列表)``。单个 Server 配置错误只会记录错误，
    不会阻止其他 Server 继续加载；整个文件损坏时抛出 :class:`MCPConfigError`。
    """
    config_path = Path(path)
    if not config_path.is_file():
        return [], []

    try:
        raw_text = config_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise MCPConfigError(f"无法读取 MCP 配置文件 {config_path}：{exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise MCPConfigError(
            f"MCP 配置文件格式错误（{config_path} 第 {exc.lineno} 行第 {exc.colno} 列）：{exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise MCPConfigError(f"MCP 配置文件 {config_path} 的根节点必须是对象。")

    servers = data.get("mcpServers", data.get("mcp_servers"))
    if servers is None:
        return [], []
    if not isinstance(servers, dict):
        raise MCPConfigError(f"MCP 配置文件 {config_path} 中的 mcpServers 必须是对象。")

    configs: list[MCPServerConfig] = []
    errors: list[str] = []
    for name, payload in servers.items():
        if not isinstance(name, str) or not name.strip():
            errors.append(f"MCP 配置错误：Server 名称必须是非空字符串（{name!r}）。")
            continue
        if isinstance(payload, dict):
            if payload.get("enabled") is False or payload.get("disabled") is True:
                continue
        try:
            configs.append(_parse_server(name.strip(), payload))
        except MCPConfigError as exc:
            errors.append(str(exc))

    return configs, errors


__all__ = [
    "DEFAULT_TIMEOUT",
    "ENV_MCP_CONFIG",
    "ENV_MCP_DISABLED",
    "MCP_CONFIG_FILENAME",
    "MCPServerConfig",
    "load_mcp_servers",
    "mcp_disabled",
    "resolve_mcp_config_path",
]
