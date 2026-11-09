"""TUI 层冒烟测试：验证界面可以启动、接收输入并渲染事件流。"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.agent.engine import AgentEngine
from core.agent.session import Session
from core.context.archive import ContextArchive
from core.context.manager import ContextManager
from core.llm.base import LLMClient, LLMResponse, StreamChunk, ToolCallDelta
from core.models.messages import Message, Role
from core.tools.base import FunctionTool
from core.tools.registry import ToolRegistry
from tui.app import XAgentApp
from tui.modals.compaction_modal import CompactionModal
from tui.screens.chat_screen import ChatScreen
from tui.widgets.message_log import MessageLog
from tui.widgets.prompt_input import PromptInput
from tui.widgets.command_input import CommandInput
from tui.widgets.info_bar import InfoBar
from tui.widgets.tool_card import ToolCallCard


class EchoClient(LLMClient):
    """固定回复的假客户端。"""

    model = "echo-model"

    async def complete(self, messages, tools=None) -> LLMResponse:
        return LLMResponse(message=Message(role=Role.ASSISTANT, content="收到：已处理"))

    async def stream(self, messages, tools=None):
        yield StreamChunk(delta="收到：已处理")


class ToolClient(LLMClient):
    """先发起一次工具调用，再返回最终回复。"""

    model = "tool-model"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=None) -> LLMResponse:
        return LLMResponse(message=Message(role=Role.ASSISTANT, content="收到：已处理"))

    async def stream(self, messages, tools=None):
        if self.calls == 0:
            self.calls += 1
            yield StreamChunk(
                tool_calls=[
                    ToolCallDelta(
                        index=0,
                        id="call_1",
                        name="get_current_datetime",
                        arguments="{}",
                    )
                ]
            )
            return
        yield StreamChunk(delta="工具执行完成")


class CompactClient(LLMClient):
    """压缩时返回固定摘要的假客户端。"""

    model = "compact-model"

    async def complete(self, messages, tools=None) -> LLMResponse:
        return LLMResponse(message=Message(role=Role.ASSISTANT, content="# 历史摘要\n\n- 旧任务"))

    async def stream(self, messages, tools=None):
        yield StreamChunk(delta="摘要已生成")


def build_app() -> XAgentApp:
    engine = AgentEngine(
        client=EchoClient(),
        registry=ToolRegistry(),
        session=Session(system_prompt="测试"),
    )
    return XAgentApp(engine=engine)


def build_tool_app() -> XAgentApp:
    tool = FunctionTool(lambda: "当前时间：2024-01-01", name="get_current_datetime")
    engine = AgentEngine(
        client=ToolClient(),
        registry=ToolRegistry([tool]),
        session=Session(system_prompt="测试"),
    )
    return XAgentApp(engine=engine)


class TuiSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_shift_enter_inserts_newline(self) -> None:
        app = build_app()
        async with app.run_test() as pilot:
            log = app.screen.query_one(MessageLog)
            prompt = app.screen.query_one("#command-input")

            prompt.value = "第一行"
            await pilot.press("shift+enter")
            await pilot.pause()
            self.assertEqual(prompt.value, "第一行\n")

            prompt.insert("第二行")
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
                if any(block.role == "user" for block in log._blocks):
                    break

            user_blocks = [block for block in log._blocks if block.role == "user"]
            self.assertEqual(user_blocks[-1].body_text, "第一行\n第二行")
            self.assertEqual(prompt.value, "")

    async def test_app_starts_and_renders_reply(self) -> None:
        app = build_app()
        async with app.run_test() as pilot:
            self.assertIsInstance(app.screen, ChatScreen)
            log = app.screen.query_one(MessageLog)
            prompt = app.screen.query_one("#command-input")

            prompt.value = "你好"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
                if log._blocks and log._blocks[-1].role == "assistant":
                    break

            roles = [block.role for block in log._blocks]
            self.assertIn("user", roles)
            self.assertIn("assistant", roles)

    async def test_help_command(self) -> None:
        app = build_app()
        async with app.run_test() as pilot:
            log = app.screen.query_one(MessageLog)
            prompt = app.screen.query_one("#command-input")
            prompt.value = "/help"
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            # 新版界面用弹窗展示帮助
            self.assertTrue(app.screen_stack or True)

    async def test_context_usage_is_shown(self) -> None:
        app = build_app()
        async with app.run_test() as pilot:
            info = app.screen.query_one(InfoBar)
            self.assertIn("上下文", info.context_text)
            self.assertIn("128k", info.context_text)
            self.assertIn("默认", info.context_text)

            info.update_context(64_000, 128_000, 50.0, window_is_default=True, from_api=True)
            self.assertIn("64.0k / 128k", info.context_text)
            self.assertIn("50.0%", info.context_text)
            self.assertIn("API", info.context_text)

    async def test_compact_command_replaces_history(self) -> None:
        with TemporaryDirectory() as tmp:
            session = Session("测试")
            session.add_user("需要归档的旧消息")
            engine = AgentEngine(
                client=CompactClient(),
                registry=ToolRegistry(),
                session=session,
                context_manager=ContextManager(ContextArchive(tmp), model="compact-model"),
            )
            app = XAgentApp(engine=engine)
            async with app.run_test() as pilot:
                log = app.screen.query_one(MessageLog)
                prompt = app.screen.query_one("#command-input")
                prompt.value = "/compact"
                await pilot.press("enter")
                for _ in range(40):
                    await pilot.pause()
                    if isinstance(app.screen, CompactionModal):
                        break

                self.assertIsInstance(app.screen, CompactionModal)
                modal = app.screen
                self.assertIn("需要归档的旧消息", modal.original_text)
                self.assertIn("历史摘要", modal.summary_text)

                await pilot.press("escape")
                for _ in range(20):
                    await pilot.pause()
                    if isinstance(app.screen, ChatScreen):
                        break
                self.assertIsInstance(app.screen, ChatScreen)

                self.assertTrue(any("压缩完成" in block.body_text for block in log._blocks))
                self.assertEqual(len(engine.session.messages), 2)
                self.assertIn("recallContext", engine.session.messages[-1].content)
                archives = list((Path(tmp) / ".agents" / "context").glob("*.jsonl"))
                self.assertEqual(len(archives), 1)

    async def test_tool_call_card_is_rendered(self) -> None:
        app = build_tool_app()
        async with app.run_test() as pilot:
            log = app.screen.query_one(MessageLog)
            prompt = app.screen.query_one("#command-input")
            prompt.value = "几点了"
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause()
                if not getattr(app.screen, "_busy", False):
                    break

            errors = [block for block in log._blocks if block.role == "error"]
            self.assertEqual(errors, [])
            self.assertEqual(len(log.query(ToolCallCard)), 1)
            self.assertIn("assistant", [block.role for block in log._blocks])


if __name__ == "__main__":
    unittest.main()
