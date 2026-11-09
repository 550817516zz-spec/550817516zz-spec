"""模型客户端抽象：core 层只依赖接口，不依赖具体厂商 SDK。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Sequence

from core.models.messages import Message


@dataclass(slots=True)
class ToolCallDelta:
    """流式场景下的工具调用增量。"""

    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""


@dataclass(slots=True)
class StreamChunk:
    """流式响应的一个数据块。"""

    delta: str = ""
    tool_calls: list[ToolCallDelta] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


@dataclass(slots=True)
class LLMResponse:
    """非流式响应。"""

    message: Message
    raw: Any = None
    usage: dict[str, Any] | None = None


class LLMClient(ABC):
    """模型客户端协议。"""

    model: str = ""

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """一次性返回完整回复。"""

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式返回回复；不支持时抛出 LLMError 由上层回退。"""
        raise NotImplementedError
