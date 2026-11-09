"""xAgent 统一异常体系。"""


class XAgentError(Exception):
    """xAgent 基础异常。"""


class ConfigurationError(XAgentError):
    """配置缺失、缺失字段或取值非法。"""


class LLMError(XAgentError):
    """模型调用失败。"""


class ToolError(XAgentError):
    """工具执行失败。"""


class ToolNotFoundError(ToolError):
    """调用了未注册的工具。"""


class MCPError(ToolError):
    """MCP 客户端基础异常。"""


class MCPConfigError(ConfigurationError):
    """`.mcp.json` 缺失、格式错误或包含不支持的配置。"""


class MCPConnectionError(MCPError):
    """MCP Server 连接、发现或调用失败。"""


class MCPToolError(MCPError):
    """MCP Server 明确返回了工具执行错误。"""


class AgentError(XAgentError):
    """Agent 运行时错误。"""
