"""课堂随手记：一个零依赖的小命令行脚本。

上课时想到什么，随手敲一行，自动带时间戳存到同目录的「课堂随手记.md」。

用法：
    python classroom_demo.py 记 "第三章：贝叶斯公式，先验 × 似然 / 证据"
    python classroom_demo.py 列表
    python classroom_demo.py 清空
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

NOTES_FILE = Path(__file__).with_name("课堂随手记.md")


def timestamp() -> str:
    """返回当前本地时间，格式 2026-11-05 11:53:29。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add(note: str) -> None:
    """追加一条笔记；文件不存在时先补一个标题。"""
    is_new_file = not NOTES_FILE.exists()
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        if is_new_file:
            f.write("# 课堂随手记\n\n")
        f.write(f"- {timestamp()} · {note}\n")
    print(f"已记下：{note}")


def list_notes() -> None:
    """打印全部笔记。"""
    if not NOTES_FILE.exists():
        print("还没有笔记，先记一条吧～")
        return
    print(NOTES_FILE.read_text(encoding="utf-8"), end="")


def clear() -> None:
    """清空笔记文件。"""
    if NOTES_FILE.exists():
        NOTES_FILE.unlink()
    print("已清空。")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0

    command, *rest = argv[1:]
    if command in ("记", "add") and rest:
        add(" ".join(rest))
    elif command in ("列表", "list"):
        list_notes()
    elif command in ("清空", "clear"):
        clear()
    else:
        print(f"未知命令：{command}\n")
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
