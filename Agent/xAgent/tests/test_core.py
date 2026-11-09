"""core 层单元测试（标准库 unittest，无需第三方依赖）。

运行方式：
    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.agent.engine import AgentEngine
from core.agent.events import (
    AssistantDeltaEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from core.agent.session import Session
from core.exceptions import ToolError
from core.llm.base import LLMClient, LLMResponse, StreamChunk, ToolCallDelta
from core.models.messages import Message, Role, ToolCall
from core.tools.base import FunctionTool, tool
from core.tools.builtin import register_builtin_tools
from core.tools.builtin.search_tools import build_search_tools
from core.tools.registry import ToolRegistry
from core.workspace import Workspace


class ScriptedClient(LLMClient):
    """按脚本返回预设响应的假客户端。"""

    def __init__(self, messages: list[Message], repeat: bool = False) -> None:
        self.model = "scripted-model"
        self._messages = list(messages)
        self._repeat = repeat
        self._last: Message | None = None
        self.requests: list[list[dict]] = []

    def _next(self) -> Message:
        if not self._messages:
            if self._repeat and self._last is not None:
                return self._last
            raise RuntimeError("脚本已耗尽")
        message = self._messages.pop(0)
        self._last = message
        return message

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.requests.append(list(messages))
        return LLMResponse(message=self._next())

    async def stream(self, messages, tools=None):
        self.requests.append(list(messages))
        message = self._next()
        for char in message.content:
            yield StreamChunk(delta=char)
        for index, call in enumerate(message.tool_calls):
            yield StreamChunk(
                tool_calls=[
                    ToolCallDelta(
                        index=index,
                        id=call.id,
                        name=call.name,
                        arguments=call.raw_arguments,
                    )
                ]
            )


def make_engine(messages: list[Message], repeat: bool = False, **kwargs) -> AgentEngine:
    registry = ToolRegistry()
    registry.register(
        FunctionTool(lambda year: "闰年", name="echo", description="回显", parameters={"type": "object", "properties": {}})
    )
    return AgentEngine(
        client=ScriptedClient(messages, repeat=repeat),
        registry=registry,
        session=Session(system_prompt="你是测试助手"),
        **kwargs,
    )


async def collect(engine: AgentEngine, text: str) -> list:
    return [event async for event in engine.run(text)]


class ToolSchemaTest(unittest.TestCase):
    def test_schema_is_derived_from_annotations_and_docstring(self) -> None:
        @tool("计算两个数之和")
        def add(left: int, right: int = 1) -> str:
            """把两个数相加。

            Args:
                left: 左操作数
                right: 右操作数
            """
            return str(left + right)

        self.assertEqual(add.name, "add")
        self.assertEqual(add.description, "计算两个数之和")
        self.assertEqual(add.parameters["properties"]["left"]["type"], "integer")
        self.assertEqual(add.parameters["properties"]["right"]["type"], "integer")
        self.assertEqual(add.parameters["properties"]["left"]["description"], "左操作数")
        self.assertEqual(add.parameters["required"], ["left"])

    def test_registry_collects_tools_and_schemas(self) -> None:
        registry = ToolRegistry()

        @registry.tool("回显")
        def echo(text: str) -> str:
            """回显文本。"""
            return text

        self.assertIn("echo", registry)
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry.get("echo").name, "echo")
        self.assertEqual(registry.schemas()[0]["function"]["name"], "echo")

    def test_builtin_tools_are_registered(self) -> None:
        registry = ToolRegistry()
        with TemporaryDirectory() as tmp:
            workspace = Workspace.from_root(tmp)
            register_builtin_tools(registry, workspace)
        names = registry.names()
        for expected in (
            "isLeapYear",
            "get_file_content",
            "create_file",
            "delete_file",
            "runAgentBrowser",
            "recallContext",
        ):
            self.assertIn(expected, names)

    def test_agent_browser_rejects_unknown_commands_and_uses_fixed_executable(self) -> None:
        from core.tools.builtin.agent_browser import build_agent_browser_tools

        with TemporaryDirectory() as tmp:
            tool_item = build_agent_browser_tools(tmp)[0]
            self.assertIn("不支持", tool_item.execute(command="powershell", arguments=["-Command", "whoami"]))
            exe = Path(tmp) / "tool" / "agent-browse" / "agent-browser-win32-x64.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch("core.tools.builtin.agent_browser.subprocess.run") as run:
                run.return_value.stdout = "ok"
                run.return_value.stderr = ""
                run.return_value.returncode = 0
                self.assertEqual(tool_item.execute(command="open", arguments=["https://example.com"]), "ok")
                self.assertEqual(run.call_args.args[0], [str(exe.resolve()), "open", "https://example.com"])
                self.assertFalse(run.call_args.kwargs["shell"])
                self.assertIn("截图路径", tool_item.execute(command="screenshot", arguments=["../../escape.png"]))


class WorkspaceTest(unittest.TestCase):
    def test_outside_root_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Workspace.from_root(tmp)
            with self.assertRaises(ToolError):
                workspace.resolve("../escape.txt")

    def test_inside_root_is_allowed(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Workspace.from_root(tmp)
            self.assertEqual(workspace.resolve("a/b.txt"), Path(tmp).resolve() / "a" / "b.txt")

    def test_read_only_blocks_write(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Workspace.from_root(tmp, read_only=True)
            with self.assertRaises(ToolError):
                workspace.ensure_writable()


class FileToolTest(unittest.TestCase):
    def test_write_outside_workspace_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Workspace.from_root(tmp)
            registry = ToolRegistry()
            register_builtin_tools(registry, workspace)
            result = registry.get("create_file").execute(directory="..", file_name="evil.txt")
            self.assertIn("失败", result)

    def test_read_write_inside_workspace(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Workspace.from_root(tmp)
            registry = ToolRegistry()
            register_builtin_tools(registry, workspace)
            created = registry.get("create_file").execute(directory="sub", file_name="a.txt")
            self.assertIn("成功", created)
            write = registry.get("edit_file_content").execute(file_path="sub/a.txt", content="hello")
            self.assertIn("成功", write)
            read = registry.get("get_file_content").execute(file_path="sub/a.txt")
            self.assertEqual(read, "hello")
            listed = registry.get("list_files_in_directory").execute(directory="sub")
            self.assertIn("a.txt", listed)
            deleted = registry.get("delete_file").execute(file_path="sub/a.txt")
            self.assertIn("成功", deleted)


class SearchToolTest(unittest.TestCase):
    def test_search_tool_is_registered_only_with_api_key(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Workspace.from_root(tmp)
            without_key = ToolRegistry()
            register_builtin_tools(without_key, workspace)
            self.assertNotIn("web_search", without_key.names())

            with_key = ToolRegistry()
            register_builtin_tools(with_key, workspace, search_api_key="test-key")
            self.assertIn("web_search", with_key.names())

    def test_missing_api_key_returns_hint(self) -> None:
        tool_item = build_search_tools("")[0]
        self.assertIn("baidu_qianfan_api_key", tool_item.execute(query="天气"))

    def test_references_are_formatted(self) -> None:
        tool_item = build_search_tools("test-key")[0]
        response = {
            "request_id": "req-1",
            "references": [
                {
                    "id": 1,
                    "title": "示例标题",
                    "url": "https://example.com/a",
                    "content": "示例摘要内容",
                    "date": "2026-10-26 12:00:00",
                }
            ],
        }
        with patch("core.tools.builtin.search_tools._post_json", return_value=response):
            result = tool_item.execute(query="示例", top_k=1)
        self.assertIn("示例标题", result)
        self.assertIn("https://example.com/a", result)
        self.assertIn("示例摘要内容", result)
        self.assertIn("2026-10-26", result)

    def test_empty_references_returns_not_found(self) -> None:
        tool_item = build_search_tools("test-key")[0]
        with patch(
            "core.tools.builtin.search_tools._post_json",
            return_value={"references": []},
        ):
            result = tool_item.execute(query="不存在的关键词")
        self.assertIn("未找到", result)


class EngineTest(unittest.TestCase):
    def test_tool_call_round_trip(self) -> None:
        call = ToolCall(id="call_1", name="echo", arguments={"year": 2024}, raw_arguments='{"year": 2024}')
        engine = make_engine(
            [
                Message(role=Role.ASSISTANT, content="", tool_calls=[call]),
                Message(role=Role.ASSISTANT, content="2024 是闰年"),
            ]
        )
        events = asyncio.run(collect(engine, "2024 是闰年吗"))

        kinds = [type(event).__name__ for event in events]
        self.assertEqual(kinds[0], "UserMessageEvent")
        self.assertIn("ToolCallEvent", kinds)
        self.assertIn("ToolResultEvent", kinds)
        self.assertEqual(kinds[-1], "DoneEvent")

        tool_result = next(e for e in events if isinstance(e, ToolResultEvent))
        self.assertTrue(tool_result.ok)
        self.assertEqual(tool_result.result, "闰年")

        final = next(e for e in events if isinstance(e, AssistantMessageEvent))
        self.assertEqual(final.text, "2024 是闰年")
        self.assertEqual(engine.session.messages[-1].content, "2024 是闰年")

    def test_streaming_deltas_are_emitted(self) -> None:
        engine = make_engine([Message(role=Role.ASSISTANT, content="你好")])
        events = asyncio.run(collect(engine, "hi"))
        deltas = [e.delta for e in events if isinstance(e, AssistantDeltaEvent)]
        self.assertEqual("".join(deltas), "你好")

    def test_unknown_tool_reports_failure(self) -> None:
        call = ToolCall(id="call_x", name="missing_tool", arguments={}, raw_arguments="{}")
        engine = make_engine(
            [
                Message(role=Role.ASSISTANT, content="", tool_calls=[call]),
                Message(role=Role.ASSISTANT, content="抱歉"),
            ]
        )
        events = asyncio.run(collect(engine, "调用不存在的工具"))
        result = next(e for e in events if isinstance(e, ToolResultEvent))
        self.assertFalse(result.ok)
        self.assertIn("未知工具", result.result)

    def test_error_event_is_emitted_on_failure(self) -> None:
        engine = make_engine([])
        events = asyncio.run(collect(engine, "boom"))
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        self.assertTrue(errors)
        self.assertTrue(any(isinstance(e, DoneEvent) for e in events))
        # 错误消息应包含底层错误信息（不再重复添加"模型请求失败"前缀）
        self.assertIn("脚本已耗尽", errors[0].message)

    def test_max_iterations_guard(self) -> None:
        call = ToolCall(id="c", name="echo", arguments={}, raw_arguments="{}")
        engine = make_engine(
            [Message(role=Role.ASSISTANT, content="", tool_calls=[call])],
            repeat=True,
            max_iterations=2,
        )
        events = asyncio.run(collect(engine, "loop"))
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        self.assertTrue(errors)
        self.assertIn("迭代次数", errors[0].message)


if __name__ == "__main__":
    unittest.main()
