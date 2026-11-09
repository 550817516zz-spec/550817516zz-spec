"""上下文压缩日志。

日志写入项目本地的 `.agents/logs/compact.log`，方便排查压缩过程。
日志失败不会影响压缩主流程。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

LOG_SUBDIR = Path(".agents") / "logs"
LOG_FILENAME = "compact.log"


def write_compact_log(
    project_root: Path | str,
    message: str,
    *,
    level: str = "INFO",
) -> None:
    """追加一条带时间戳的压缩日志。"""
    try:
        path = Path(project_root) / LOG_SUBDIR / LOG_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{level}] {message}\n")
    except OSError:
        # 日志只是辅助信息，写入失败时不能影响上下文压缩。
        pass
