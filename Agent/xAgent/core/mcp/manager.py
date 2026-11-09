"""MCP Server 发现、工具注册与生命周期管理。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from core.exceptions import MCPConfigError, MCPError
from core.mcp.config import (
    MCPServerConfig,
    load_mcp_servers,
    mcp_disabled,
    resolve_mcp_config_path,
)
from core.mcp.tools import MCPTool, build_mcp_tool, safe_tool_name
from core.mcp.transport import MCPConnection, describe_exception
from core.tools.registry import ToolRegistry

_MAX_LENGTH = 64


class MCPManager:
    """管理多个 MCP Server 连接，并把工具注册进现有工具表。"""

    def __init__(
        self,
        project_root: Path | str | None = None,
        config_path: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root or Path.cwd()).expanduser().resolve()
        self.config_path = resolve_mcp_config_path(self.project_root, config_path)
        self.servers: dict[str, MCPServerConfig] = {}
        self.connections: dict[str, MCPConnection] = {}
        self.errors: list[str] = []
        # 暴露给 LLM 的工具名 -> (Server 名, 远端工具名)
        self.tool_map: dict[str, tuple[str, str]] = {}
        # Server 名 -> (远端工具名 -> 暴露给 LLM 的工具名)
        self.server_tool_map: dict[str, dict[str, str]] = {}
        self.tools: list[MCPTool] = []
        self._remote_tools: list[tuple[MCPConnection, Any]] = []
        self._connected = False
        self._registered = False
        self._closed = False

    # ------------------------------------------------------------------
    # 连接与发现
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """读取配置并连接所有启用的 Server；单个失败不会影响其他 Server。"""
        if self._connected:
            return
        self._connected = True

        if mcp_disabled():
            return
        if not self.config_path.is_file():
            return

        try:
            configs, config_errors = load_mcp_servers(self.config_path)
        except MCPConfigError as exc:
            self._add_error(str(exc))
            return
        for message in config_errors:
            self._add_error(message)

        for config in configs:
            self.servers[config.name] = config
            connection = MCPConnection(config)
            try:
                connection.start()
            except Exception as exc:  # noqa: BLE001 - 单 Server 失败不影响其他工具
                message = (
                    str(exc)
                    if isinstance(exc, MCPError)
                    else f"MCP Server「{config.name}」连接失败：{describe_exception(exc)}"
                )
                self._add_error(message)
                try:
                    connection.close()
                except Exception:
                    pass
                continue

            self.connections[config.name] = connection
            for remote_tool in connection.tools:
                remote_name = self._remote_name(remote_tool)
                if not remote_name:
                    self._add_error(
                        f"MCP Server「{config.name}」返回了一个没有名称的工具，已跳过。"
                    )
                    continue
                self._remote_tools.append((connection, remote_tool))

    def register_tools(self, registry: ToolRegistry) -> None:
        """把已发现工具注册到 xAgent 工具表，并处理名称冲突。"""
        if self._registered:
            return
        self._registered = True

        used = set(registry.names())
        for connection, remote_tool in self._remote_tools:
            server_name = connection.name
            remote_name = self._remote_name(remote_tool)
            base = safe_tool_name(remote_name)
            if base in used:
                # 与本地工具或其他 Server 冲突时，加服务器前缀。
                base = safe_tool_name(f"{safe_tool_name(server_name)}_{remote_name}")

            exposed = base
            index = 2
            while exposed in used:
                suffix = f"_{index}"
                exposed = safe_tool_name(base[: _MAX_LENGTH - len(suffix)] + suffix)
                index += 1

            tool = build_mcp_tool(
                server_name=server_name,
                remote_tool=remote_tool,
                exposed_name=exposed,
                connection=connection,
            )
            registry.register(tool)
            self.tools.append(tool)
            used.add(exposed)
            self.tool_map[exposed] = (server_name, remote_name)
            self.server_tool_map.setdefault(server_name, {})[remote_name] = exposed

    def register(self, registry: ToolRegistry) -> "MCPManager":
        """连接并注册，返回自身便于链式调用。"""
        self.connect()
        self.register_tools(registry)
        return self

    # ------------------------------------------------------------------
    # 查询与报告
    # ------------------------------------------------------------------
    @property
    def connected_servers(self) -> list[str]:
        return [
            name
            for name, connection in self.connections.items()
            if connection.connected
        ]

    def resolve_tool(self, exposed_name: str) -> tuple[str, str] | None:
        """把 LLM 看到的工具名还原为 ``(server, remote_tool)``。"""
        return self.tool_map.get(exposed_name)

    def status_lines(self) -> list[str]:
        lines: list[str] = []
        for name, connection in self.connections.items():
            tools = ", ".join(self.server_tool_map.get(name, {}).values()) or "无可用工具"
            lines.append(f"MCP Server「{name}」已连接；工具：{tools}。")
        return lines

    def report_errors(self, stream: TextIO | None = None) -> None:
        """把连接/调用错误输出到 stderr（或指定流）。"""
        target = stream or sys.stderr
        for message in self.errors:
            print(f"[MCP] {message}", file=target)

    def _add_error(self, message: str) -> None:
        if message and message not in self.errors:
            self.errors.append(message)

    @staticmethod
    def _remote_name(remote_tool: Any) -> str:
        if isinstance(remote_tool, dict):
            return str(remote_tool.get("name") or "")
        return str(getattr(remote_tool, "name", "") or "")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def close(self) -> None:
        """关闭所有连接；可重复调用。"""
        if self._closed:
            return
        self._closed = True
        for connection in list(self.connections.values()):
            try:
                connection.close()
            except Exception:
                pass


def register_mcp_tools(
    registry: ToolRegistry,
    *,
    project_root: Path | str | None = None,
    config_path: Path | str | None = None,
    manager: MCPManager | None = None,
    report_errors: bool = True,
) -> MCPManager:
    """构建/复用 MCPManager，连接 Server 并注册工具。

    读取的默认配置文件是 ``<project_root>/.mcp.json``；``project_root``
    缺省为当前工作目录。返回的 Manager 需要随应用生命周期关闭。
    """
    active = manager or MCPManager(project_root=project_root, config_path=config_path)
    active.register(registry)
    if report_errors:
        active.report_errors()
    return active


__all__ = ["MCPManager", "register_mcp_tools"]
