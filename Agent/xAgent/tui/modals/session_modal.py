"""Keyboard-selectable list of saved sessions."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option


class SessionModal(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss(None)", "取消")]

    def __init__(self, sessions: list[dict[str, str]]) -> None:
        super().__init__()
        self.sessions = sessions

    def compose(self) -> ComposeResult:
        options = [Option(f"{item['title'] or '未命名'}  ·  {item['updated_at']}  ·  {item['id']}", id=item['id'])
                   for item in self.sessions]
        yield Vertical(
            Label("恢复历史会话（↑↓ 选择，Enter 恢复，Esc 取消）", classes="help-title"),
            OptionList(*options, id="session-options"),
            classes="help-dialog",
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        self.dismiss(str(option_id) if option_id else None)
