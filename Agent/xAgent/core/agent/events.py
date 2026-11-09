"""Agent 事件：core 层向任意前端输出统一的流式协议。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, kw_only=True)
class AgentEvent:
    """所有事件的基类。"""

    timestamp: float = field(default_factory=time.time)

    @property
    def type(self) -> str:
        return type(self).__name__


@dataclass(slots=True, kw_only=True)
class UserMessageEvent(AgentEvent):
    """用户输入已被接收。"""

    text: str = ""


@dataclass(slots=True, kw_only=True)
class AssistantDeltaEvent(AgentEvent):
    """助手回复的增量文本。"""

    delta: str = ""


@dataclass(slots=True, kw_only=True)
class AssistantMessageEvent(AgentEvent):
    """助手完整回复。"""

    text: str = ""


@dataclass(slots=True, kw_only=True)
class ToolCallEvent(AgentEvent):
    """模型发起工具调用。"""

    call_id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class ToolResultEvent(AgentEvent):
    """工具执行结果。"""

    call_id: str = ""
    name: str = ""
    result: str = ""
    ok: bool = True


@dataclass(slots=True, kw_only=True)
class ContextStatusEvent(AgentEvent):
    """上下文占用情况更新。"""

    used_tokens: int = 0
    window_tokens: int = 0
    percent: float = 0.0
    window_is_default: bool = False
    from_api: bool = False
    compact_required: bool = False


@dataclass(slots=True, kw_only=True)
class ContextWarningEvent(AgentEvent):
    """上下文达到阈值时的警告。"""

    message: str = ""
    percent: float = 0.0


@dataclass(slots=True, kw_only=True)
class CompactionStartedEvent(AgentEvent):
    """上下文压缩开始或阶段进展。"""

    archive_id: str = ""
    message: str = ""


@dataclass(slots=True, kw_only=True)
class CompactionFinishedEvent(AgentEvent):
    """上下文压缩成功完成。"""

    archive_id: str = ""
    summary_tokens: int = 0
    message: str = ""
    original_text: str = ""
    summary_text: str = ""


@dataclass(slots=True, kw_only=True)
class ErrorEvent(AgentEvent):
    """执行过程中出现的错误。"""

    message: str = ""


@dataclass(slots=True, kw_only=True)
class DoneEvent(AgentEvent):
    """一轮对话结束。"""

    text: str = ""
