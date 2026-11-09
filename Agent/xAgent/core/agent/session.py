"""会话：管理一轮对话的消息历史。"""

from __future__ import annotations

from typing import Any

from core.models.messages import Message, Role, ToolCall


class Session:
    """保存消息历史，可序列化以便存档。"""

    def __init__(self, system_prompt: str | None = None) -> None:
        self.system_prompt = system_prompt
        self._messages: list[Message] = []
        if system_prompt:
            self._messages.append(Message(role=Role.SYSTEM, content=system_prompt))

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    @property
    def system_messages(self) -> list[Message]:
        return [item for item in self._messages if item.role is Role.SYSTEM]

    def add_user(self, text: str) -> Message:
        message = Message(role=Role.USER, content=text)
        self._messages.append(message)
        return message

    def add_agents_instructions(self, text: str) -> Message:
        """Append project instructions as a reusable, separately persisted system message."""
        marker = "<!-- xagent:AGENTS.md -->"
        content = f"{marker}\n{text}"
        for existing in self._messages:
            if existing.role is Role.SYSTEM and marker in existing.content:
                return existing
        message = Message(role=Role.SYSTEM, content=content)
        self._messages.append(message)
        return message

    def add_assistant(self, message: Message) -> Message:
        self._messages.append(message)
        return message

    def add_tool_result(self, call: ToolCall, content: str) -> Message:
        message = Message(
            role=Role.TOOL,
            content=content,
            tool_call_id=call.id,
            name=call.name,
        )
        self._messages.append(message)
        return message

    def update_system_prompt(self, prompt: str) -> None:
        """替换系统提示词，并同步更新历史中的系统消息。"""
        self.system_prompt = prompt
        indexes = [
            index for index, message in enumerate(self._messages) if message.role is Role.SYSTEM
        ]
        if not indexes:
            self._messages.insert(0, Message(role=Role.SYSTEM, content=prompt))
            return
        self._messages[indexes[0]] = Message(role=Role.SYSTEM, content=prompt)
        for index in reversed(indexes[1:]):
            del self._messages[index]

    def reset(self) -> None:
        """清空历史但保留系统提示词。"""
        system = self.system_messages
        self._messages = list(system)

    def replace_history_with_summary(self, summary: str) -> Message:
        """用压缩摘要替换历史消息，保留 System Prompt 与工具定义。"""
        self._messages = list(self.system_messages)
        message = Message(role=Role.ASSISTANT, content=summary)
        self._messages.append(message)
        return message

    def restore_messages(self, messages: list[Message]) -> None:
        """恢复一组消息，用于压缩失败时回滚。"""
        self._messages = list(messages)

    def api_messages(self) -> list[dict[str, Any]]:
        return [message.to_api() for message in self._messages]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "messages": [message.to_api() for message in self._messages],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Session":
        session = cls(system_prompt=payload.get("system_prompt"))
        session._messages = [Message.from_api(item) for item in payload.get("messages", [])]
        return session
