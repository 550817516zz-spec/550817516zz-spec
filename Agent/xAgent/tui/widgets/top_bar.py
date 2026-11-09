"""窗口标题栏组件。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static


class TopBar(Horizontal):
    """顶部标题栏：左侧应用信息，中间工作目录，右侧时间。"""

    time_text = reactive("")

    def __init__(
        self,
        app_name: str = "xAgent",
        model: str = "",
        workspace: Path | None = None,
    ) -> None:
        super().__init__(classes="topbar")
        self.app_name = app_name
        self.model = model
        self.workspace = workspace or Path.cwd()
        self._left = Static("", classes="topbar-left")
        self._mid = Static("", classes="topbar-mid")
        self._right = Static("", classes="topbar-right")

    def compose(self) -> ComposeResult:
        yield self._left
        yield self._mid
        yield self._right

    def on_mount(self) -> None:
        self._update()
        self.set_interval(1, self._update)

    def _update(self) -> None:
        self._left.update(f"{self.app_name} — {self.model}")
        self._mid.update(str(self.workspace))
        self._right.update(datetime.now().strftime("%H:%M:%S"))

    def update_model(self, model: str) -> None:
        self.model = model
        self._update()

    def update_workspace(self, workspace: Path) -> None:
        self.workspace = workspace
        self._update()
