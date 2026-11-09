"""输入区：Enter 发送，Shift+Enter 换行。"""

from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import TextArea
from textual import events


class CommandInput(TextArea):
    """底部命令输入框，支持多行输入。"""

    BINDINGS = [
        Binding("enter", "submit", show=False, priority=True),
        Binding("shift+enter", "newline", show=False, priority=True),
        Binding("ctrl+enter", "newline", show=False, priority=True),
        Binding("ctrl+j", "newline", show=False, priority=True),
    ]

    class Submitted(Message):
        """用户提交输入内容。"""

        def __init__(self, input: "CommandInput", value: str) -> None:
            super().__init__()
            self.input = input
            self.value = value

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault(
            "placeholder",
            "输入消息后 Enter 发送，Shift+Enter（或 Ctrl+J）换行；/help 查看命令",
        )
        kwargs.setdefault("id", "command-input")
        kwargs.setdefault("show_line_numbers", False)
        super().__init__(**kwargs)
        self.can_focus = True

    @property
    def value(self) -> str:
        return self.text

    @value.setter
    def value(self, value: str) -> None:
        self.load_text(value)
        lines = value.split("\n")
        self.move_cursor((len(lines) - 1, len(lines[-1])))

    def on_mount(self) -> None:
        self.focus()

    def action_submit(self) -> None:
        value = self.text.strip()
        if value:
            self.post_message(self.Submitted(self, value))

    def action_newline(self) -> None:
        self.insert("\n")

    def on_key(self, event: events.Key) -> None:
        if event.key in ("up", "down"):
            return
        self.post_message(self.Changed(self, self.text))

    class Changed(Message):
        def __init__(self, input: "CommandInput", value: str) -> None:
            super().__init__()
            self.input = input
            self.value = value
