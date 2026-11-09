"""xAgent 核心层：与界面无关的领域逻辑与基础设施。

分层约定：
- core.agent      业务编排层（事件流、循环控制）
- core.tools      能力层（工具抽象、注册表、内置工具）
- core.llm        基础设施层（模型客户端抽象与实现）
- core.config     基础设施层（配置装载）
- core.models     领域模型
"""

from core.agent.engine import AgentEngine
from core.agent.events import (
    AgentEvent,
    AssistantDeltaEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from core.agent.session import Session
from core.bootstrap import (
    build_client,
    build_engine,
    build_registry,
    build_session,
    build_skill_manager,
    build_workspace,
)
from core.config.settings import Settings, load_settings
from core.exceptions import (
    AgentError,
    ConfigurationError,
    LLMError,
    ToolError,
    ToolNotFoundError,
    XAgentError,
)
from core.llm.base import LLMClient, LLMResponse, StreamChunk, ToolCallDelta
from core.llm.openai_client import OpenAICompatibleClient
from core.models.messages import Message, Role, ToolCall
from core.skills import Skill, SkillManager
from core.tools.base import FunctionTool, Tool, tool
from core.tools.registry import ToolRegistry
from core.workspace import Workspace

__all__ = [
    "AgentEngine",
    "AgentError",
    "AgentEvent",
    "AssistantDeltaEvent",
    "AssistantMessageEvent",
    "ConfigurationError",
    "DoneEvent",
    "ErrorEvent",
    "FunctionTool",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "Message",
    "OpenAICompatibleClient",
    "Role",
    "Session",
    "Settings",
    "Skill",
    "SkillManager",
    "StreamChunk",
    "Tool",
    "ToolCall",
    "ToolCallDelta",
    "ToolCallEvent",
    "ToolError",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolResultEvent",
    "UserMessageEvent",
    "Workspace",
    "XAgentError",
    "build_client",
    "build_engine",
    "build_registry",
    "build_session",
    "build_skill_manager",
    "build_workspace",
    "load_settings",
    "tool",
]
