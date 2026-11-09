"""顶部信息条：显示工具数、模型、工作目录、快捷键提示。"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class InfoBar(Vertical):
    """青蓝色边框的顶部信息框。"""

    def __init__(
        self,
        app_name: str = "xAgent",
        tool_count: int = 0,
        model: str = "",
        workspace: Path | None = None,
    ) -> None:
        super().__init__(classes="infobar")
        self.app_name = app_name
        self.tool_count = tool_count
        self.model = model
        self.workspace = workspace or Path.cwd()
        self._row1 = Static("", classes="infobar-row")
        self._row_ctx = Static("", classes="infobar-row infobar-context")
        self._context_text = ""
        self._row2 = Static("", classes="infobar-row")
        self._row3 = Static(
            "Enter 发送　Shift+Enter 换行　/help 命令　Esc 中断生成　Ctrl+B 侧栏　Ctrl+N 新会话",
            classes="infobar-row infobar-keys",
        )

    def compose(self) -> ComposeResult:
        yield self._row1
        yield self._row_ctx
        yield self._row2
        yield self._row3

    def on_mount(self) -> None:
        self._update()

    def _update(self) -> None:
        self._row1.update(f"{self.app_name} · {self.tool_count} 个工具 · {self.model}")
        self._row2.update(f"工作目录 {self.workspace}")

    def update_meta(self, tool_count: int | None = None, model: str | None = None, workspace: Path | None = None) -> None:
        if tool_count is not None:
            self.tool_count = tool_count
        if model is not None:
            self.model = model
        if workspace is not None:
            self.workspace = workspace
        self._update()

    def update_context(
        self,
        used_tokens: int,
        window_tokens: int,
        percent: float,
        *,
        window_is_default: bool = False,
        compact_required: bool = False,
        from_api: bool = False,
    ) -> None:
        """醒目地显示上下文占用：当前 k / 窗口 k（百分比）。"""
        used_k = used_tokens / 1000
        window_k = window_tokens / 1000
        source = "API" if from_api else "估算"
        default = " · 默认" if window_is_default else ""
        line = (
            f"上下文 {used_k:.1f}k / {window_k:.0f}k"
            f"（{percent:.1f}%）· {source}{default}"
        )
        self._context_text = line
        if compact_required:
            line = f"⚠ {line} · 已达阈值，请输入 /compact"
            self._row_ctx.update(f"[bold red]{line}[/]")
        elif percent >= 50:
            self._row_ctx.update(f"[yellow]{line}[/]")
        else:
            self._row_ctx.update(f"[cyan]{line}[/]")

    @property
    def context_text(self) -> str:
        """当前显示的上下文摘要文本（便于测试/外部读取）。"""
        return self._context_text
