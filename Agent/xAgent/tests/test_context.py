"""上下文压缩、归档与检索的单元测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.agent.engine import AgentEngine
from core.agent.events import (
    CompactionFinishedEvent,
    ErrorEvent,
    UserMessageEvent,
)
from core.agent.session import Session
from core.context.archive import ContextArchive, build_recall_tool
from core.context.manager import ContextManager
from core.context.tokens import estimate_text_tokens, resolve_context_window
from core.llm.base import LLMClient, LLMResponse, StreamChunk
from core.models.messages import Message, Role, ToolCall
from core.tools.registry import ToolRegistry


class CompactionClient(LLMClient):
    """压缩时返回固定摘要的假客户端。"""

    model = "compact-model"

    def __init__(self) -> None:
        self.compact_requests: list[tuple[list[dict], object]] = []

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.compact_requests.append((list(messages), tools))
        return LLMResponse(
            message=Message(role=Role.ASSISTANT, content="# 工作摘要\n\n- 用户要求保留暗号。"),
            usage={"total_tokens": 120},
        )

    async def stream(self, messages, tools=None):
        yield StreamChunk(delta="ok")


def build_history(session: Session) -> ToolCall:
    session.add_user("请记住暗号 ABC123，并读取 secret.txt。")
    call = ToolCall(
        id="call_1",
        name="get_file_content",
        arguments={"file_path": "secret.txt"},
        raw_arguments='{"file_path": "secret.txt"}',
    )
    session.add_assistant(Message(role=Role.ASSISTANT, content="", tool_calls=[call]))
    session.add_tool_result(call, "文件内容：关键线索 ABC123")
    return call


class TokenTest(unittest.TestCase):
    def test_estimate_text_tokens(self) -> None:
        self.assertGreater(estimate_text_tokens("你好世界"), 0)
        self.assertGreater(estimate_text_tokens("hello world"), 0)
        self.assertEqual(estimate_text_tokens(""), 0)

    def test_window_resolution(self) -> None:
        self.assertEqual(resolve_context_window("unknown-model"), (128_000, True))
        self.assertEqual(resolve_context_window("deepseek-chat"), (64_000, False))
        self.assertEqual(resolve_context_window("x", 32_000), (32_000, False))


class ArchiveTest(unittest.TestCase):
    def test_save_preserves_messages_and_search_finds_tool_result(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = ContextArchive(tmp)
            session = Session("你是测试助手")
            build_history(session)
            archive_id = archive.save(session.messages)

            path = Path(tmp) / ".agents" / "context" / f"{archive_id}.jsonl"
            self.assertTrue(path.is_file())
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([item["index"] for item in records], [0, 1, 2, 3])
            self.assertEqual(records[1]["role"], "user")
            self.assertEqual(records[2]["tool_calls"][0]["function"]["name"], "get_file_content")
            self.assertEqual(records[3]["role"], "tool")
            self.assertEqual(records[3]["tool_call_id"], "call_1")

            result = archive.search("ABC123")
            self.assertIn(archive_id, result)
            self.assertIn("role=tool", result)
            self.assertIn("ABC123", result)

            specific = archive.search("ABC123", archive_id=archive_id)
            self.assertIn(archive_id, specific)
            self.assertIn("未找到", archive.search("完全不存在的关键词"))

    def test_archive_id_cannot_escape_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = ContextArchive(tmp)
            session = Session("系统")
            session.add_user("内容")
            archive.save(session.messages)
            self.assertIn("未找到归档", archive.search("内容", archive_id="../../evil"))

    def test_recall_tool_schema(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = ContextArchive(tmp)
            session = Session("系统")
            session.add_user("需要检索的历史内容")
            archive_id = archive.save(session.messages)

            tool_item = build_recall_tool(archive)
            self.assertEqual(tool_item.name, "recallContext")
            self.assertEqual(tool_item.parameters["required"], ["text"])
            self.assertIn("id", tool_item.parameters["properties"])
            result = tool_item.execute(text="历史内容", id=archive_id)
            self.assertIn(archive_id, result)


class ManagerTest(unittest.TestCase):
    def test_threshold_sets_requires_compaction(self) -> None:
        with TemporaryDirectory() as tmp:
            manager = ContextManager(
                ContextArchive(tmp),
                model="unknown",
                context_window=1000,
            )
            session = Session("系统")
            session.add_user("很长" * 800)
            stats = manager.measure(session)
            self.assertTrue(stats.compact_required)
            self.assertTrue(manager.requires_compaction)
            self.assertIsNotNone(manager.warning_for(stats))
            self.assertIsNone(manager.warning_for(stats))

            manager.reset_after_compaction()
            self.assertFalse(manager.requires_compaction)

    def test_api_usage_is_used_when_available(self) -> None:
        with TemporaryDirectory() as tmp:
            manager = ContextManager(
                ContextArchive(tmp),
                model="unknown",
                context_window=10_000,
            )
            session = Session("系统")
            session.add_user("你好")
            session.add_assistant(Message(role=Role.ASSISTANT, content="你好"))
            manager.record_api_usage({"total_tokens": 500}, len(session.messages))
            stats = manager.measure(session)
            self.assertTrue(stats.from_api)
            self.assertGreaterEqual(stats.used_tokens, 500)


class EngineCompactionTest(unittest.IsolatedAsyncioTestCase):
    async def test_compact_archives_and_replaces_history(self) -> None:
        with TemporaryDirectory() as tmp:
            client = CompactionClient()
            session = Session("你是测试助手")
            build_history(session)
            archive = ContextArchive(tmp)
            engine = AgentEngine(
                client=client,
                registry=ToolRegistry(),
                session=session,
                context_manager=ContextManager(
                    archive,
                    model="unknown",
                    context_window=1000,
                ),
            )

            events = [event async for event in engine.compact()]
            finished = [event for event in events if isinstance(event, CompactionFinishedEvent)]
            self.assertEqual(len(finished), 1)
            archive_id = finished[0].archive_id
            self.assertTrue((Path(tmp) / ".agents" / "context" / f"{archive_id}.jsonl").is_file())
            self.assertIn("ABC123", finished[0].original_text)
            self.assertIn("工作摘要", finished[0].summary_text)
            log_text = (Path(tmp) / ".agents" / "logs" / "compact.log").read_text(encoding="utf-8")
            self.assertIn("压缩成功", log_text)
            self.assertIn(archive_id, log_text)

            # 压缩只调用一次 LLM，且不传任何工具定义。
            self.assertEqual(len(client.compact_requests), 1)
            sent_messages, sent_tools = client.compact_requests[0]
            self.assertIsNone(sent_tools)
            self.assertIn("上下文管理助手", sent_messages[0]["content"])
            self.assertIn("ABC123", sent_messages[1]["content"])

            messages = engine.session.messages
            self.assertEqual(messages[0].role, Role.SYSTEM)
            self.assertEqual(len(messages), 2)
            self.assertIn("工作摘要", messages[-1].content)
            self.assertIn("recallContext", messages[-1].content)
            self.assertIn(archive_id, messages[-1].content)
            self.assertFalse(engine.context.requires_compaction)
            self.assertIn("ABC123", archive.search("ABC123", archive_id=archive_id))

    async def test_compact_failure_keeps_original_context(self) -> None:
        with TemporaryDirectory() as tmp:
            client = CompactionClient()
            session = Session("你是测试助手")
            build_history(session)
            engine = AgentEngine(
                client=client,
                registry=ToolRegistry(),
                session=session,
                context_manager=ContextManager(ContextArchive(tmp), model="unknown"),
            )
            before = [(item.role, item.content) for item in session.messages]
            with patch.object(engine.context.archive, "save", side_effect=OSError("磁盘已满")):
                events = [event async for event in engine.compact()]
            errors = [event for event in events if isinstance(event, ErrorEvent)]
            self.assertTrue(errors)
            self.assertIn("压缩失败", errors[0].message)
            after = [(item.role, item.content) for item in session.messages]
            self.assertEqual(before, after)
            log_text = (Path(tmp) / ".agents" / "logs" / "compact.log").read_text(encoding="utf-8")
            self.assertIn("压缩失败", log_text)

    async def test_threshold_blocks_new_prompts(self) -> None:
        with TemporaryDirectory() as tmp:
            client = CompactionClient()
            engine = AgentEngine(
                client=client,
                registry=ToolRegistry(),
                session=Session("你是测试助手"),
                context_manager=ContextManager(ContextArchive(tmp), model="unknown"),
            )
            engine.context.requires_compaction = True
            events = [event async for event in engine.run("继续任务")]
            self.assertTrue(any(isinstance(event, ErrorEvent) for event in events))
            self.assertFalse(any(isinstance(event, UserMessageEvent) for event in events))
            self.assertEqual(len(engine.session.messages), 1)


if __name__ == "__main__":
    unittest.main()
