"""消息流容器。"""

from __future__ import annotations

import json
from typing import Any

from textual.containers import VerticalScroll

from tui.widgets.message_block import MessageBlock

TOOL_RESULT_LIMIT = 800


def format_arguments(arguments: dict[str, Any]) -> str:
    """把工具入参压缩成一行易读文本。"""
    parts = []
    for key, value in arguments.items():
        parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    return ", ".join(parts)


def truncate(text: str, limit: int = TOOL_RESULT_LIMIT) -> str:
    """超长结果截断，避免刷屏。"""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（已截断，共 {len(text)} 字符）"


class MessageLog(VerticalScroll):
    """按时间顺序展示对话消息的滚动容器。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._blocks: list[MessageBlock] = []

    async def append(self, block: MessageBlock) -> MessageBlock:
        self._blocks.append(block)
        await self.mount(block)
        self.scroll_end(animate=False)
        return block

    async def append_user(self, text: str) -> MessageBlock:
        block = MessageBlock("user", "你", renderer="text")
        block.update_body(text)
        return await self.append(block)

    async def append_assistant(self, text: str = "") -> MessageBlock:
        block = MessageBlock("assistant", "xAgent")
        block.update_body(text)
        return await self.append(block)

    async def append_tool(self, name: str, arguments: dict[str, Any] | None = None) -> MessageBlock:
        block = MessageBlock("tool", name, renderer="text")
        if arguments:
            block.update_body(format_arguments(arguments))
        return await self.append(block)

    async def append_tool_result(self, name: str, result: str, ok: bool = True) -> MessageBlock:
        block = MessageBlock("tool", f"{name} {'✓' if ok else '✗'}", renderer="text")
        block.update_body(truncate(result))
        return await self.append(block)

    async def append_error(self, text: str) -> MessageBlock:
        block = MessageBlock("error", "错误", renderer="text")
        block.update_body(text)
        return await self.append(block)

    async def append_notice(self, text: str) -> MessageBlock:
        block = MessageBlock("system", "系统", renderer="text")
        block.update_body(text)
        return await self.append(block)

    async def clear(self) -> None:
        self._blocks.clear()
        await self.remove_children()
