"""对话数据模型：与具体模型厂商无关的中间表示。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    """消息角色。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(slots=True)
class ToolCall:
    """模型发起的一次工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.raw_arguments or json.dumps(self.arguments, ensure_ascii=False),
            },
        }

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ToolCall":
        function = raw.get("function") or {}
        raw_arguments = function.get("arguments") or ""
        try:
            arguments = json.loads(raw_arguments) if raw_arguments else {}
        except (TypeError, ValueError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}
        return cls(
            id=raw.get("id") or "",
            name=function.get("name") or "",
            arguments=arguments,
            raw_arguments=raw_arguments,
        )


@dataclass(slots=True)
class Message:
    """一条对话消息。"""

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role.value, "content": self.content or None}
        if self.tool_calls:
            payload["tool_calls"] = [call.to_api() for call in self.tool_calls]
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.name:
            payload["name"] = self.name
        return payload

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Message":
        role_value = raw.get("role") or Role.USER.value
        try:
            role = Role(role_value)
        except ValueError:
            role = Role.USER
        tool_calls = [ToolCall.from_api(item) for item in raw.get("tool_calls") or []]
        return cls(
            role=role,
            content=raw.get("content") or "",
            tool_calls=tool_calls,
            tool_call_id=raw.get("tool_call_id"),
            name=raw.get("name"),
        )
