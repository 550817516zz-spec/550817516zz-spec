"""xAgent 的 Textual 应用外壳。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from textual.app import App

from core.agent.engine import AgentEngine
from tui.screens.chat_screen import ChatScreen


def _driver_class():
    if sys.platform == "win32":
        from tui.windows_driver import XAgentWindowsDriver

        return XAgentWindowsDriver
    return None


class XAgentApp(App):
    """终端界面入口，只负责装配与生命周期，不含业务逻辑。"""

    CSS_PATH = "styles.tcss"
    TITLE = "xAgent"
    SUB_TITLE = "模块化 LLM Agent"

    def __init__(self, engine: AgentEngine, workspace: Path | None = None) -> None:
        super().__init__(driver_class=_driver_class())
        self.engine = engine
        self.workspace = workspace or Path.cwd()

    async def on_mount(self) -> None:
        await self.push_screen(ChatScreen(engine=self.engine, workspace=self.workspace))

    async def on_unmount(self) -> None:
        try:
            await asyncio.to_thread(self.engine.close)
        except Exception:
            pass
        close = getattr(self.engine.client, "aclose", None)
        if close is None:
            return
        try:
            await close()
        except Exception:
            pass
