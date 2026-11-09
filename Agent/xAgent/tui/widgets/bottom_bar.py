"""底部状态栏：状态 + 轮次 + 模型 + 工具次数 + 耗时。"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class BottomStatusBar(Horizontal):
    """底部状态栏与快捷键信息。"""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "bottombar")
        super().__init__(classes="bottombar", **kwargs)
        self._status = Static("● 就绪", classes="bottombar-status")
        self._info = Static("", classes="bottombar-info")
        self._keys = Static("Enter 发送　Shift+Enter 换行　^q 退出　^l 清屏　^n 新会话　^b 侧栏　f1 帮助", classes="bottombar-keys")
        self._palette = Static("^p palette", classes="bottombar-palette")
        self._start = time.perf_counter()
        self._rounds = 0
        self._tool_calls = 0

    def compose(self) -> ComposeResult:
        yield self._status
        yield self._info
        yield self._keys
        yield self._palette

    def start_round(self) -> None:
        self._start = time.perf_counter()
        self._rounds += 1
        self._status.update("● 思考中")
        self._update_info()

    def add_tool_call(self) -> None:
        self._tool_calls += 1
        self._update_info()

    def end_round(self, model: str = "") -> None:
        elapsed = time.perf_counter() - self._start
        self._status.update("● 就绪")
        info = f"{self._rounds} 轮　{model}　工具 {self._tool_calls} 次　{elapsed:.1f}s　Esc 中断"
        self._info.update(info)

    def reset(self) -> None:
        self._rounds = 0
        self._tool_calls = 0
        self._status.update("● 就绪")
        self._info.update("")

    def _update_info(self) -> None:
        elapsed = time.perf_counter() - self._start
        self._info.update(f"{self._rounds} 轮　工具 {self._tool_calls} 次　{elapsed:.1f}s")
