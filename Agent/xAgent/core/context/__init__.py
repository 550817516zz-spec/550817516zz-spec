"""上下文压缩与历史归档。

这个包只依赖 core.models，负责三件事：

1. 估算当前会话占用的 Token；
2. 在压缩前把原始上下文保存成 JSONL 归档；
3. 提供 recallContext 工具使用的本地全文检索。
"""

from core.context.archive import ContextArchive, build_recall_tool
from core.context.log import write_compact_log
from core.context.manager import ContextManager, ContextStats
from core.context.tokens import (
    COMPACT_TARGET_TOKENS,
    COMPACT_THRESHOLD,
    DEFAULT_CONTEXT_WINDOW,
    estimate_messages_tokens,
    resolve_context_window,
)

__all__ = [
    "COMPACT_TARGET_TOKENS",
    "COMPACT_THRESHOLD",
    "DEFAULT_CONTEXT_WINDOW",
    "ContextArchive",
    "ContextManager",
    "ContextStats",
    "build_recall_tool",
    "estimate_messages_tokens",
    "resolve_context_window",
    "write_compact_log",
]
