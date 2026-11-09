"""Agent 引擎：ReAct 式循环，对外只暴露事件流。

核心层不感知任何界面，Web / Desktop / Mobile 前端只需消费 `AgentEngine.run()`
产生的异步事件流即可实现与 TUI 完全一致的功能。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

from core.agent.events import (
    AgentEvent,
    AssistantDeltaEvent,
    AssistantMessageEvent,
    CompactionFinishedEvent,
    CompactionStartedEvent,
    ContextStatusEvent,
    ContextWarningEvent,
    DoneEvent,
    ErrorEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from core.agent.session import Session
from core.context.archive import archive_time_text
from core.context.log import write_compact_log
from core.context.manager import ContextManager, ContextStats
from core.context.prompt import COMPACTION_PROMPT
from core.context.tokens import estimate_text_tokens
from core.exceptions import AgentError, LLMError, ToolError
from core.llm.base import LLMClient, StreamChunk, ToolCallDelta
from core.models.messages import Message, Role, ToolCall
from core.tools.registry import ToolRegistry


@dataclass(slots=True)
class _ToolCallBuffer:
    """流式工具调用的累积缓冲。"""

    id: str = ""
    name: str = ""
    arguments: str = ""

    def merge(self, delta: ToolCallDelta) -> None:
        if delta.id:
            self.id = delta.id
        if delta.name:
            self.name = delta.name
        if delta.arguments:
            self.arguments += delta.arguments

    def to_tool_call(self) -> ToolCall:
        try:
            arguments = json.loads(self.arguments) if self.arguments.strip() else {}
        except (TypeError, ValueError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}
        return ToolCall(
            id=self.id or f"call_{uuid.uuid4().hex[:12]}",
            name=self.name,
            arguments=arguments,
            raw_arguments=self.arguments,
        )


def _format_transcript(messages: list[Message]) -> str:
    """把完整消息序列整理成供压缩模型阅读的 JSONL 文本。"""
    lines: list[str] = []
    for index, message in enumerate(messages):
        payload: dict[str, Any] = {
            "index": index,
            "role": message.role.value,
            "content": message.content or "",
        }
        if message.tool_calls:
            payload["tool_calls"] = [call.to_api() for call in message.tool_calls]
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.name:
            payload["name"] = message.name
        lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines)


def _format_preview(messages: list[Message]) -> str:
    """把消息整理成适合在压缩详情面板中阅读的纯文本。"""
    role_labels = {
        Role.SYSTEM: "系统提示",
        Role.USER: "用户",
        Role.ASSISTANT: "助手",
        Role.TOOL: "工具",
    }
    blocks: list[str] = []
    for index, message in enumerate(messages, start=1):
        label = role_labels.get(message.role, message.role.value)
        header = f"[{index}] {label}"
        if message.name:
            header += f" · {message.name}"
        if message.tool_call_id:
            header += f" · tool_call_id={message.tool_call_id}"

        body = message.content or "（空）"
        if message.tool_calls:
            calls = [
                {"name": call.name, "arguments": call.arguments}
                for call in message.tool_calls
            ]
            body += "\n\n工具调用：\n" + json.dumps(calls, ensure_ascii=False, indent=2)
        blocks.append(f"{header}\n{body}")
    return ("\n\n" + "-" * 60 + "\n\n").join(blocks)


class AgentEngine:
    """编排模型调用与工具执行。"""

    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        session: Session | None = None,
        *,
        max_iterations: int = 8,
        stream_enabled: bool = True,
        mcp_manager: Any | None = None,
        context_manager: ContextManager | None = None,
        project_root: Any | None = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_iterations = max(1, max_iterations)
        self.stream_enabled = stream_enabled
        self.session = session or Session()
        self.mcp_manager = mcp_manager
        self.project_root = project_root
        self.context = context_manager or ContextManager(model=getattr(client, "model", ""))
        self._pending_usage: dict[str, Any] | None = None
        self._compacting = False

    @property
    def tool_names(self) -> list[str]:
        return self.registry.names()

    @property
    def mcp_errors(self) -> list[str]:
        return list(getattr(self.mcp_manager, "errors", []) or [])

    def mcp_status_lines(self) -> list[str]:
        status = getattr(self.mcp_manager, "status_lines", None)
        if not callable(status):
            return []
        try:
            return list(status())
        except Exception:
            return []

    def load_mcp(self) -> list[str]:
        """Connect MCP servers and register their tools after the UI is mounted."""
        if self.mcp_manager is None:
            return []
        try:
            self.mcp_manager.register(self.registry)
        except Exception as exc:
            return [f"MCP 加载失败：{type(exc).__name__}: {exc}"]
        return self.mcp_status_lines() + self.mcp_errors

    def close(self) -> None:
        """释放工具注册表关联的资源（包括 MCP 连接）。"""
        self.registry.close()
        if self.mcp_manager is not None:
            try:
                self.mcp_manager.close()
            except Exception:
                pass

    async def run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """处理一次用户输入，按顺序产出事件。"""
        text = (user_input or "").strip()
        if not text:
            return

        if self._compacting:
            yield ErrorEvent(message="上下文压缩正在进行，请稍后再试。")
            yield DoneEvent()
            return
        if self.context.requires_compaction:
            yield ErrorEvent(
                message=(
                    "当前上下文已达到压缩阈值，暂时不能接受新的提示词。"
                    "请先执行 /compact 完成上下文压缩。"
                )
            )
            yield DoneEvent()
            return

        self.session.add_user(text)
        yield UserMessageEvent(text=text)

        reply = ""
        try:
            async for event in self._turn():
                if isinstance(event, AssistantMessageEvent):
                    reply = event.text
                yield event
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 不再重复添加前缀；LLMError 已包含可操作的中文消息
            yield ErrorEvent(message=str(exc))

        yield DoneEvent(text=reply)

    async def _turn(self) -> AsyncIterator[AgentEvent]:
        for _ in range(self.max_iterations):
            content_parts: list[str] = []
            buffers: dict[int, _ToolCallBuffer] = {}

            try:
                async for chunk in self._stream_once():
                    if chunk.delta:
                        content_parts.append(chunk.delta)
                        yield AssistantDeltaEvent(delta=chunk.delta)
                    for delta in chunk.tool_calls:
                        buffer = buffers.setdefault(delta.index, _ToolCallBuffer())
                        buffer.merge(delta)
            except Exception as exc:
                if content_parts:
                    content = "".join(content_parts)
                    self.session.add_assistant(
                        Message(role=Role.ASSISTANT, content=content, tool_calls=[])
                    )
                    yield AssistantMessageEvent(text=content)
                    return
                msg = str(exc)
                if "generator didn't stop" in msg or "接收响应体" in msg:
                    raise AgentError("网络流中断，请重试") from exc
                raise

            content = "".join(content_parts)
            tool_calls = [buffers[index].to_tool_call() for index in sorted(buffers)]

            self.session.add_assistant(
                Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)
            )
            self.context.record_api_usage(self._pending_usage, len(self.session.messages))
            for context_event in self._context_events():
                yield context_event

            if not tool_calls:
                yield AssistantMessageEvent(text=content)
                return

            for call in tool_calls:
                yield ToolCallEvent(call_id=call.id, name=call.name, arguments=call.arguments)

            for call in tool_calls:
                # 工具可能包含阻塞式网络请求，放到线程中执行以免卡住事件循环。
                result, ok = await asyncio.to_thread(self._execute_tool, call)
                yield ToolResultEvent(
                    call_id=call.id,
                    name=call.name,
                    result=result,
                    ok=ok,
                )
                self.session.add_tool_result(call, result)

            # 工具结果会显著增加上下文长度，因此每轮工具执行后重新检查。
            for context_event in self._context_events():
                yield context_event

        raise AgentError(f"已达到最大迭代次数（{self.max_iterations}），本轮中止。")

    async def _stream_once(self) -> AsyncIterator[StreamChunk]:
        """优先使用流式接口，失败时回退到一次性接口。

        连接类错误（端口未监听、代理拦截、DNS 失败等）不会因换一种
        请求方式而好转，回退只会产生第二次无效请求并掩盖真正的错误原因，
        因此对这类错误直接抛出，不回退。
        """
        messages = self.session.api_messages()
        schemas = self.registry.schemas()
        self._pending_usage = None

        if self.stream_enabled:
            emitted = False
            try:
                async for chunk in self.client.stream(messages, schemas):
                    emitted = emitted or bool(chunk.delta)
                    if chunk.usage:
                        self._pending_usage = chunk.usage
                    yield chunk
                return
            except (LLMError, NotImplementedError) as exc:
                if emitted:
                    raise
                # 连接类错误不回退到非流式——换一种请求方式不会改善连接问题
                error_text = str(exc)
                connection_keywords = (
                    "连接被拒绝", "连接超时", "无法连接", "连接模型服务失败",
                    "请求超时", "读取响应超时", "无法连接到模型服务",
                )
                if any(kw in error_text for kw in connection_keywords):
                    raise

        response = await self.client.complete(messages, schemas)
        self._pending_usage = response.usage
        message = response.message
        tool_deltas = [
            ToolCallDelta(
                index=index,
                id=call.id,
                name=call.name,
                arguments=call.raw_arguments or json.dumps(call.arguments, ensure_ascii=False),
            )
            for index, call in enumerate(message.tool_calls)
        ]
        yield StreamChunk(
            delta=message.content or "",
            tool_calls=tool_deltas,
            usage=response.usage,
        )

    def _context_events(self) -> list[AgentEvent]:
        """测量上下文并生成状态/警告事件。"""
        stats = self.context.measure(self.session, self.registry.schemas())
        events: list[AgentEvent] = [
            ContextStatusEvent(
                used_tokens=stats.used_tokens,
                window_tokens=stats.window_tokens,
                percent=stats.percent,
                window_is_default=stats.window_is_default,
                from_api=stats.from_api,
                compact_required=stats.compact_required,
            )
        ]
        warning = self.context.warning_for(stats)
        if warning:
            events.append(ContextWarningEvent(message=warning, percent=stats.percent))
        return events

    def context_stats(self) -> ContextStats:
        """供前端在空闲时读取当前上下文占用。"""
        return self.context.measure(self.session, self.registry.schemas())

    def reset_session(self) -> None:
        """清空会话并解除上下文压缩限制。"""
        self.session.reset()
        self.context.reset_after_compaction()

    def _compact_log(self, message: str, *, level: str = "INFO") -> None:
        write_compact_log(self.context.archive.project_root, message, level=level)

    async def compact(self) -> AsyncIterator[AgentEvent]:
        """手动触发上下文压缩。

        压缩期间只调用一次 LLM（不传工具定义），不会执行任何其他工具。
        """
        if self._compacting:
            self._compact_log("忽略重复的压缩请求：上一次压缩仍在进行", level="WARNING")
            yield ErrorEvent(message="上下文压缩正在进行，请稍后再试。")
            yield DoneEvent()
            return

        self._compacting = True
        original_messages: list[Message] = []
        replaced = False
        try:
            messages = self.session.messages
            original_messages = list(messages)
            if not any(message.role is not Role.SYSTEM for message in messages):
                self._compact_log("跳过压缩：当前没有可压缩的对话历史", level="WARNING")
                yield ErrorEvent(message="当前没有可压缩的对话历史。")
            else:
                stats = self.context.measure(self.session, self.registry.schemas())
                self._compact_log(
                    f"开始压缩：消息 {len(messages)} 条，"
                    f"上下文 {stats.used_k:.1f}k/{stats.window_k:.0f}k"
                    f"（{stats.percent:.1f}%）"
                )
                yield CompactionStartedEvent(message="正在保存原始上下文…")
                archive_id = await asyncio.to_thread(self.context.archive.save, messages)
                self._compact_log(
                    f"原始上下文已归档：{archive_id}.jsonl（{len(messages)} 条消息）"
                )
                yield CompactionStartedEvent(
                    archive_id=archive_id,
                    message=f"原始上下文已保存到归档 {archive_id}，正在调用模型生成摘要…",
                )

                self._compact_log("调用 LLM 生成上下文摘要（未传工具定义）")
                response = await self.client.complete(
                    [
                        {"role": "system", "content": COMPACTION_PROMPT},
                        {
                            "role": "user",
                            "content": "以下是需要压缩的历史上下文：\n\n" + _format_transcript(messages),
                        },
                    ],
                    None,
                )
                summary = (response.message.content or "").strip()
                if not summary:
                    raise AgentError("模型未返回有效摘要。")

                note = (
                    f"> 此前上下文已于 {archive_time_text(archive_id)} 完成压缩，"
                    f"原始上下文保存在编号为 {archive_id} 的归档文件中。"
                    "如需查找历史信息，请使用 recallContext 工具。"
                )
                summary_tokens = estimate_text_tokens(summary)
                final_summary = f"{summary}\n\n---\n\n{note}"
                self._compact_log(f"摘要生成完成：约 {summary_tokens} tokens")
                preview_text = _format_preview(messages)
                self.session.replace_history_with_summary(final_summary)
                replaced = True
                self.context.reset_after_compaction()

                for context_event in self._context_events():
                    yield context_event
                new_stats = self.context.measure(self.session, self.registry.schemas())
                self._compact_log(
                    f"压缩成功：归档 {archive_id}，"
                    f"消息 {len(messages)} -> {len(self.session.messages)}，"
                    f"新上下文 {new_stats.used_k:.1f}k/{new_stats.window_k:.0f}k"
                    f"（{new_stats.percent:.1f}%）"
                )
                yield CompactionFinishedEvent(
                    archive_id=archive_id,
                    summary_tokens=summary_tokens,
                    message=(
                        f"上下文压缩完成：摘要约 {summary_tokens} tokens，"
                        f"原始上下文归档编号 {archive_id}。"
                    ),
                    original_text=preview_text,
                    summary_text=final_summary,
                )
        except asyncio.CancelledError:
            self._compact_log("压缩被取消", level="WARNING")
            raise
        except Exception as exc:
            self._compact_log(
                f"压缩失败：{type(exc).__name__}: {exc}",
                level="ERROR",
            )
            if replaced:
                # 摘要替换之后若发生意外，恢复原始消息，保证压缩失败不丢上下文。
                self.session.restore_messages(original_messages)
                self.context.reset_after_compaction()
                # 重新评估占用，避免回滚后误解除阈值限制。
                self.context.measure(self.session, self.registry.schemas())
            yield ErrorEvent(
                message=(
                    f"上下文压缩失败：{exc}。原有上下文已保留，"
                    "可以重新执行 /compact。"
                )
            )
        finally:
            self._compacting = False

        yield DoneEvent()

    def _execute_tool(self, call: ToolCall) -> tuple[str, bool]:
        target = self.registry.get(call.name)
        if target is None:
            return f"未知工具调用：{call.name}", False
        try:
            result = target.execute(**call.arguments)
        except ToolError as exc:
            return f"工具执行失败：{exc}", False
        except TypeError as exc:
            return f"工具参数不匹配：{exc}", False
        except Exception as exc:
            return f"工具执行异常：{type(exc).__name__}: {exc}", False
        return result, True
