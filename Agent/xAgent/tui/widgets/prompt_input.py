"""底部输入框：Enter 发送，Shift+Enter 换行。"""

from __future__ import annotations

from tui.widgets.command_input import CommandInput


class PromptInput(CommandInput):
    """对话输入框。"""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "prompt-input")
        super().__init__(**kwargs)
