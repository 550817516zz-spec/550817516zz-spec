"""消息展示块。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Markdown, Static

ROLE_PREFIX: dict[str, str] = {
    "user": "›",
    "assistant": "»",
    "tool": "◆",
    "error": "!",
    "system": "·",
}


class MessageBlock(Vertical):
    """一条消息的展示单元：角色前缀 + 标题 + 正文。"""

    def __init__(
        self,
        role: str,
        label: str,
        *,
        renderer: str = "markdown",
        prefix: str | None = None,
    ) -> None:
        super().__init__(classes=f"message message-{role}")
        self.role = role
        self.renderer = renderer
        self._text = ""
        self._prefix = ROLE_PREFIX.get(role, "") if prefix is None else prefix
        self._label_text = label
        self._label = Static(self._render_label(), classes="message-label")
        if renderer == "markdown":
            self._body: Static | Markdown = Markdown("", classes="message-body")
        else:
            self._body = Static("", classes="message-body message-body-text", markup=False)

    def compose(self) -> ComposeResult:
        yield self._label
        yield self._body

    @property
    def body_text(self) -> str:
        return self._text

    @property
    def label_text(self) -> str:
        return self._label_text

    def _render_label(self) -> str:
        if self._prefix:
            return f"{self._prefix} {self._label_text}"
        return self._label_text

    def update_body(self, text: str) -> None:
        self._text = text
        self._body.update(text)

    def update_label(self, text: str) -> None:
        self._label_text = text
        self._label.update(self._render_label())
