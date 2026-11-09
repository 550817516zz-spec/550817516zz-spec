"""上下文压缩详情浮层：左侧原文，右侧摘要。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class CompactionModal(ModalScreen[None]):
    """展示压缩前后的对照内容，两栏均可滚动。"""

    BINDINGS = [Binding("escape", "dismiss", "关闭")]

    def __init__(
        self,
        original_text: str,
        summary_text: str,
        *,
        archive_id: str = "",
        summary_tokens: int = 0,
    ) -> None:
        super().__init__()
        self.original_text = original_text or "（无）"
        self.summary_text = summary_text or "（无）"
        self.archive_id = archive_id
        self.summary_tokens = summary_tokens

    def compose(self) -> ComposeResult:
        meta = f"归档编号：{self.archive_id or '-'}　摘要约 {self.summary_tokens} tokens"
        with Vertical(classes="compaction-dialog"):
            yield Label("上下文压缩详情", classes="compaction-title")
            yield Label(meta, classes="compaction-meta")
            with Horizontal(classes="compaction-body"):
                with Vertical(classes="compaction-column"):
                    yield Label("压缩前原文", classes="compaction-column-title")
                    with VerticalScroll(classes="compaction-scroll"):
                        yield Static(
                            self.original_text,
                            classes="compaction-text",
                            markup=False,
                        )
                with Vertical(classes="compaction-column"):
                    yield Label("压缩后结果", classes="compaction-column-title")
                    with VerticalScroll(classes="compaction-scroll"):
                        yield Static(
                            self.summary_text,
                            classes="compaction-text",
                            markup=False,
                        )
            with Horizontal(classes="compaction-footer"):
                yield Button("关闭", id="close-compaction", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-compaction":
            self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
