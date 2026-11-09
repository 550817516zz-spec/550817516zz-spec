"""上下文长度监控。

优先使用模型 API 返回的 usage 统计；拿不到时回退到本地估算。
达到阈值后设置 requires_compaction，引擎据此拒绝新的普通用户提示词。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from core.context.archive import ContextArchive
from core.context.tokens import (
    COMPACT_THRESHOLD,
    DEFAULT_CONTEXT_WINDOW,
    MESSAGE_OVERHEAD,
    estimate_messages_tokens,
    estimate_tools_tokens,
    resolve_context_window,
)

if TYPE_CHECKING:
    from core.agent.session import Session


@dataclass(slots=True)
class ContextStats:
    """一次上下文测量的结果。"""

    used_tokens: int
    window_tokens: int
    percent: float
    window_is_default: bool
    from_api: bool
    compact_required: bool

    @property
    def used_k(self) -> float:
        return self.used_tokens / 1000

    @property
    def window_k(self) -> float:
        return self.window_tokens / 1000


class ContextManager:
    """跟踪当前会话的上下文占用，并决定何时禁止继续对话。"""

    def __init__(
        self,
        archive: ContextArchive | None = None,
        *,
        model: str = "",
        context_window: int | None = None,
        threshold: float = COMPACT_THRESHOLD,
        default_window: int = DEFAULT_CONTEXT_WINDOW,
        message_overhead: int = MESSAGE_OVERHEAD,
        archive_subdir: str = ".agents/context",
    ) -> None:
        self.archive = archive or ContextArchive(Path.cwd(), directory=archive_subdir)
        self.model = model
        self.window_tokens, self.window_is_default = resolve_context_window(
            model, context_window, default_window
        )
        self.threshold = min(max(threshold, 0.1), 1.0)
        self.message_overhead = max(0, message_overhead)
        self.requires_compaction = False
        self._usage_total: int | None = None
        self._usage_message_count = 0
        self._warned = False

    def record_api_usage(
        self,
        usage: dict[str, Any] | None,
        message_count: int,
    ) -> None:
        """记录模型 API 返回的 token 用量及其对应的消息数量。"""
        if not usage:
            return
        total = usage.get("total_tokens")
        if total is None:
            prompt = usage.get("prompt_tokens") or 0
            completion = usage.get("completion_tokens") or 0
            total = prompt + completion
        try:
            total = int(total)
        except (TypeError, ValueError):
            return
        if total < 0:
            return
        self._usage_total = total
        self._usage_message_count = message_count

    def reset_usage(self) -> None:
        """清空 API usage 基线，下一次测量会从头估算。"""
        self._usage_total = None
        self._usage_message_count = 0

    def reset_after_compaction(self) -> None:
        """压缩或清空会话后解除限制。"""
        self.reset_usage()
        self.requires_compaction = False
        self._warned = False

    def measure(
        self,
        session: Session,
        tool_schemas: Iterable[dict[str, Any]] | None = None,
    ) -> ContextStats:
        """测量会话当前的 Token 占用。"""
        messages = session.messages
        if self._usage_total is not None and self._usage_message_count <= len(messages):
            # API usage 对应的是上一次请求；此后新增的消息用估算补齐。
            extra = messages[self._usage_message_count :]
            used = self._usage_total + estimate_messages_tokens(extra, self.message_overhead)
            from_api = True
        else:
            used = estimate_messages_tokens(messages, self.message_overhead) + estimate_tools_tokens(tool_schemas)
            from_api = False

        used = max(0, int(used))
        percent = (used / self.window_tokens * 100.0) if self.window_tokens else 0.0
        if percent >= self.threshold * 100:
            self.requires_compaction = True
        return ContextStats(
            used_tokens=used,
            window_tokens=self.window_tokens,
            percent=percent,
            window_is_default=self.window_is_default,
            from_api=from_api,
            compact_required=self.requires_compaction,
        )

    def warning_for(self, stats: ContextStats) -> str | None:
        """达到阈值时返回一次警告文本；同一段上下文只警告一次。"""
        if stats.percent < self.threshold * 100:
            return None
        if self._warned:
            return None
        self._warned = True
        default_hint = (
            "（未能识别模型窗口大小，按默认 128k 计算）"
            if stats.window_is_default
            else ""
        )
        return (
            f"⚠ 当前上下文已使用 {stats.used_k:.1f}k / {stats.window_k:.0f}k"
            f"（{stats.percent:.1f}%），达到 {self.threshold * 100:.0f}% 阈值"
            f"{default_hint}。请执行 /compact 压缩上下文；"
            "压缩成功前将暂停接受新的普通提示词。"
        )
