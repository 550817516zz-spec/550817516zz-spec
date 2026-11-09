"""工具调用卡片（可折叠风格）。"""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

MAX_PREVIEW = 600


class ToolCallCard(Vertical):
    """绿色边框的工具执行卡片，支持展开/折叠展示。"""

    expanded = reactive(True)

    def __init__(self, name: str, arguments: dict[str, Any] | None = None, duration_ms: int | None = None) -> None:
        super().__init__(classes="toolcard")
        self.tool_name = name
        self.arguments = arguments or {}
        self.duration_ms = duration_ms
        self.result_text = ""
        self.ok = True
        self._header = Static("", classes="toolcard-header")
        self._params_label = Static("参数", classes="toolcard-section-label")
        self._params = Static("", classes="toolcard-params")
        self._result_label = Static("结果", classes="toolcard-section-label")
        self._result = Static("", classes="toolcard-result", markup=False)
        self._refresh_display()

    def compose(self) -> ComposeResult:
        yield self._header
        yield self._params_label
        yield self._params
        yield self._result_label
        yield self._result

    def on_mount(self) -> None:
        self._refresh_display()

    def _header_text(self) -> str:
        arrow = "▾" if self.expanded else "▸"
        if self.duration_ms is not None:
            return f"{arrow} ⌄ {self.tool_name}{self._args_summary()} · {self.duration_ms} ms"
        return f"{arrow} ⌄ {self.tool_name}{self._args_summary()}"

    def _args_summary(self) -> str:
        if not self.arguments:
            return "()"
        if len(self.arguments) == 1 and "year" in self.arguments:
            return f"(year={self.arguments['year']})"
        parts = []
        for key, value in self.arguments.items():
            if isinstance(value, str) and len(value) > 32:
                parts.append(f"{key}={value[:32]}…")
            else:
                parts.append(f"{key}={value}")
        return f"({', '.join(parts)})"

    def _refresh_display(self) -> None:
        self._header.update(self._header_text())
        if not self.expanded:
            self._params_label.display = False
            self._params.display = False
            self._result_label.display = False
            self._result.display = False
            return
        self._params_label.display = True
        self._params.display = True
        if self.arguments:
            self._params.update(json.dumps(self.arguments, ensure_ascii=False, indent=2))
        else:
            self._params.update("{}")
        self._result_label.display = True
        self._result.display = True
        text = self.result_text
        if len(text) > MAX_PREVIEW and not text.count("\n") > 20:
            self._result.update(text[:MAX_PREVIEW] + "\n…（已截断）")
        else:
            self._result.update(text)

    def set_result(self, result: str, ok: bool = True, duration_ms: int | None = None) -> None:
        self.result_text = result
        self.ok = ok
        if duration_ms is not None:
            self.duration_ms = duration_ms
        self._refresh_display()

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self._refresh_display()

    def watch_expanded(self) -> None:
        self._refresh_display()
