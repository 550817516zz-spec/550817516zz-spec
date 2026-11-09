"""底部状态栏。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import LoadingIndicator, Static


class StatusBar(Horizontal):
    """展示运行状态与运行环境信息。"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._spinner = LoadingIndicator(classes="status-spinner")
        self._spinner.display = False
        self._status = Static("就绪", classes="status-text")
        self._meta = Static("", classes="status-meta")

    def compose(self) -> ComposeResult:
        yield self._spinner
        yield self._status
        yield self._meta

    def set_status(self, text: str) -> None:
        self._status.update(text)

    def set_meta(self, text: str) -> None:
        self._meta.update(text)

    def set_busy(self, busy: bool) -> None:
        self._spinner.display = busy
