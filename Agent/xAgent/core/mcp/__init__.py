"""MCP（Model Context Protocol）客户端能力。

对外入口：
- :class:`MCPManager`：读取项目目录下的 ``.mcp.json``，连接 Streamable HTTP
  Server，发现并注册工具；
- :func:`register_mcp_tools`：一步完成连接与注册；
- :class:`MCPTool`：注册到 xAgent 工具表中的 MCP 工具代理。
"""

from core.mcp.config import MCPServerConfig, load_mcp_servers, resolve_mcp_config_path
from core.mcp.manager import MCPManager, register_mcp_tools
from core.mcp.tools import MCPTool, format_tool_result, safe_tool_name

__all__ = [
    "MCPServerConfig",
    "MCPManager",
    "MCPTool",
    "format_tool_result",
    "load_mcp_servers",
    "register_mcp_tools",
    "resolve_mcp_config_path",
    "safe_tool_name",
]
