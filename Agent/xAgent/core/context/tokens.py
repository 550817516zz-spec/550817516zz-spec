"""Token 估算与模型上下文窗口解析。

优先使用模型 API 返回的 usage；只有在拿不到 usage 时才使用这里的估算。
估算规则刻意保持简单：

- 中文、日文、韩文等 CJK 字符按 1 字符 ≈ 1 token；
- 其他字符按 4 字符 ≈ 1 token；
- 每条消息额外加少量结构开销。

它不是精确的 tokenizer，只用于在本地快速判断上下文是否接近上限。
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Iterable

DEFAULT_CONTEXT_WINDOW = 128_000
COMPACT_THRESHOLD = 0.70
COMPACT_TARGET_TOKENS = 5_000
MESSAGE_OVERHEAD = 4

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def estimate_text_tokens(text: str | None) -> int:
    """估算一段文本的 Token 数。"""
    if not text:
        return 0
    cjk_count = len(_CJK_RE.findall(text))
    other_count = len(text) - cjk_count
    return cjk_count + math.ceil(other_count / 4)


def estimate_message_tokens(message: Any, message_overhead: int = MESSAGE_OVERHEAD) -> int:
    """估算一条消息的 Token 数（包含工具调用参数）。"""
    total = message_overhead + estimate_text_tokens(getattr(message, "content", "") or "")
    for call in getattr(message, "tool_calls", None) or []:
        total += message_overhead
        total += estimate_text_tokens(getattr(call, "name", "") or "")
        raw = getattr(call, "raw_arguments", "") or ""
        if not raw:
            try:
                raw = json.dumps(getattr(call, "arguments", {}) or {}, ensure_ascii=False)
            except (TypeError, ValueError):
                raw = str(getattr(call, "arguments", ""))
        total += estimate_text_tokens(raw)
    return total


def estimate_messages_tokens(
    messages: Iterable[Any],
    message_overhead: int = MESSAGE_OVERHEAD,
) -> int:
    """估算一组消息的总 Token 数。"""
    return sum(
        estimate_message_tokens(message, message_overhead) for message in messages
    )


def estimate_tools_tokens(tool_schemas: Iterable[dict[str, Any]] | None) -> int:
    """估算工具定义占用的 Token 数。"""
    schemas = list(tool_schemas or [])
    if not schemas:
        return 0
    try:
        raw = json.dumps(schemas, ensure_ascii=False)
    except (TypeError, ValueError):
        return 0
    return estimate_text_tokens(raw)


# 常见模型的上下文窗口。键按小写子串匹配；这里只收录较稳定的常见名称。
# 未命中的模型会回退到 DEFAULT_CONTEXT_WINDOW，并在界面上标记“默认”。
_KNOWN_WINDOWS: tuple[tuple[str, int], ...] = (
    ("deepseek", 64_000),
    ("gpt-4.1", 1_047_576),
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-3.5", 16_385),
    ("claude", 200_000),
    ("gemini", 1_048_576),
    ("qwen", 131_072),
    ("glm", 128_000),
    ("llama", 131_072),
    ("mistral", 128_000),
)
_OPENAI_O_SERIES = ("o1", "o3", "o4")


def resolve_context_window(
    model: str | None,
    configured: int | None = None,
    default: int = DEFAULT_CONTEXT_WINDOW,
) -> tuple[int, bool]:
    """返回 (上下文窗口大小, 是否使用了默认值)。

    优先级：显式配置 > 常见模型表 > 可配置的默认值。
    """
    if configured is not None and int(configured) > 0:
        return int(configured), False

    name = (model or "").strip().lower()
    if name.startswith(_OPENAI_O_SERIES):
        return 200_000, False
    for keyword, window in _KNOWN_WINDOWS:
        if keyword in name:
            return window, False
    return max(1, int(default)), True
