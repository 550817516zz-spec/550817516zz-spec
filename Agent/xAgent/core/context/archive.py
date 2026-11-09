"""原始上下文归档与本地全文检索。

压缩前的完整消息会写入 `.agents/context/<编号>.jsonl`，一行一条消息，
保留角色、正文、工具调用参数、工具返回结果和原始顺序。

检索使用最简单的本地关键词匹配，不依赖向量数据库或 Embedding。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Sequence

from core.models.messages import Message
from core.tools.base import FunctionTool

CONTEXT_SUBDIR = Path(".agents") / "context"
MAX_HITS = 20
MAX_TOTAL_CHARS = 6_000
SNIPPET_CHARS = 300
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def archive_time_text(archive_id: str) -> str:
    """把归档编号转换成可读时间；异常编号回退到当前时间。"""
    parts = archive_id.split("-")
    if len(parts) >= 2:
        try:
            moment = datetime.strptime(f"{parts[0]}-{parts[1]}", "%Y%m%d-%H%M%S")
            return moment.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ContextArchive:
    """管理 `.agents/context/` 下的 JSONL 归档。"""

    def __init__(self, project_root: Path | str, directory: str | Path = CONTEXT_SUBDIR) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self._directory = Path(directory)

    @property
    def directory(self) -> Path:
        return (self.project_root / self._directory).resolve()

    def archive_ids(self) -> list[str]:
        """按编号从新到旧返回所有归档。"""
        if not self.directory.is_dir():
            return []
        ids = [path.stem for path in self.directory.glob("*.jsonl") if path.is_file()]
        return sorted(ids, reverse=True)

    def _next_id(self) -> str:
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = base
        suffix = 2
        while (self.directory / f"{candidate}.jsonl").exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def save(self, messages: Sequence[Message]) -> str:
        """保存完整原始上下文，成功返回归档编号。

        先写入临时文件再原子替换，确保返回编号时文件已经完整落盘。
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        archive_id = self._next_id()
        target = self.directory / f"{archive_id}.jsonl"
        temp = self.directory / f".{archive_id}.jsonl.tmp"
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                for index, message in enumerate(messages):
                    record = self._to_record(index, message)
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except BaseException:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return archive_id

    @staticmethod
    def _to_record(index: int, message: Message) -> dict[str, Any]:
        record: dict[str, Any] = {
            "index": index,
            "role": message.role.value,
            "content": message.content or "",
        }
        if message.tool_calls:
            record["tool_calls"] = [call.to_api() for call in message.tool_calls]
        if message.tool_call_id:
            record["tool_call_id"] = message.tool_call_id
        if message.name:
            record["name"] = message.name
        return record

    def _resolve_id(self, archive_id: str) -> str | None:
        value = (archive_id or "").strip()
        if value.endswith(".jsonl"):
            value = value[:-6]
        if not value or not _SAFE_ID_RE.fullmatch(value):
            return None
        return value

    def _iter_records(self, archive_id: str) -> Iterator[tuple[int, dict[str, Any]]]:
        path = self.directory / f"{archive_id}.jsonl"
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict):
                        yield line_number, record
        except OSError:
            return

    @staticmethod
    def _hit_terms(text: str) -> list[str]:
        terms = [item.casefold() for item in re.split(r"\s+", text.strip()) if item]
        return terms or [text.casefold()]

    @staticmethod
    def _searchable(record: dict[str, Any]) -> str:
        parts = [str(record.get("content") or "")]
        if record.get("tool_calls"):
            parts.append(json.dumps(record["tool_calls"], ensure_ascii=False))
        if record.get("name"):
            parts.append(str(record["name"]))
        return "\n".join(parts)

    @staticmethod
    def _snippet(record: dict[str, Any], term: str) -> str:
        content = str(record.get("content") or "")
        source = content
        position = source.casefold().find(term)
        if position < 0 and record.get("tool_calls"):
            source = json.dumps(record["tool_calls"], ensure_ascii=False)
            position = source.casefold().find(term)
        if position < 0:
            source = content or json.dumps(record, ensure_ascii=False)
            position = 0

        start = max(0, position - SNIPPET_CHARS // 3)
        end = min(len(source), start + SNIPPET_CHARS)
        snippet = source[start:end].replace("\r", " ").replace("\n", " ").strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(source):
            snippet += "…"
        return snippet

    def search(self, text: str, archive_id: str | None = None) -> str:
        """在指定或全部归档中做关键词检索。"""
        query = (text or "").strip()
        if not query:
            return "请提供需要查找的关键词或文本内容。"

        if archive_id:
            resolved = self._resolve_id(archive_id)
            path = self.directory / f"{resolved}.jsonl" if resolved else None
            if path is None or not path.is_file():
                available = "、".join(self.archive_ids()) or "无"
                return f"未找到归档：{archive_id}。可用归档：{available}"
            ids = [resolved]
        else:
            ids = self.archive_ids()

        if not ids:
            return (
                f"尚未找到任何上下文归档（目录：{self.directory}）。"
                "可能还没有执行过 /compact。"
            )

        terms = self._hit_terms(query)
        hits: list[tuple[int, str, int, dict[str, Any], str]] = []
        for current_id in ids:
            for line_number, record in self._iter_records(current_id):
                haystack = self._searchable(record).casefold()
                matched = [term for term in terms if term in haystack]
                if not matched:
                    continue
                score = sum(haystack.count(term) for term in matched)
                snippet = self._snippet(record, matched[0])
                hits.append((score, current_id, line_number, record, snippet))

        if not hits:
            scope = f"归档 {ids[0]}" if archive_id else "全部归档"
            return f"在{scope}中未找到与「{query}」匹配的内容。"

        total_matches = len(hits)
        # 相关度高的片段优先，其次保持较新的归档靠前。
        hits.sort(key=lambda item: (item[0], item[1]), reverse=True)
        hits = hits[:MAX_HITS]
        header = f"在 {len(ids)} 个归档中找到 {total_matches} 条匹配（按相关度排序）："
        blocks: list[str] = []
        total_chars = 0
        omitted = 0
        for index, (_, current_id, line_number, record, snippet) in enumerate(hits):
            role = str(record.get("role") or "unknown")
            block = (
                f"[归档 {current_id} · 消息 #{line_number} · role={role}]\n"
                f"{snippet}"
            )
            if blocks and total_chars + len(block) > MAX_TOTAL_CHARS:
                omitted = total_matches - index
                break
            blocks.append(block)
            total_chars += len(block)

        omitted = max(omitted, total_matches - len(blocks))
        footer = ""
        if omitted:
            footer = (
                f"\n\n…还有 {omitted} 条匹配未显示。"
                "请使用更精确的关键词或通过 id 指定归档以缩小范围。"
            )
        return header + "\n\n" + "\n\n".join(blocks) + footer


def build_recall_tool(archive: ContextArchive) -> FunctionTool:
    """构建 recallContext 工具。"""

    def recallContext(text: str, id: str | None = None) -> str:
        """检索此前上下文压缩时保存的原始对话记录。

        当压缩摘要缺少某些历史细节时，用它查找原始消息、工具调用参数或工具返回结果。

        Args:
            text: 需要查找的关键词或文本内容
            id: 可选，指定要检索的归档编号；省略时检索 .agents/context/ 下所有归档
        """
        return archive.search(text=text, archive_id=id)

    return FunctionTool(
        recallContext,
        name="recallContext",
        description=(
            "检索此前上下文压缩时保存的原始对话记录。"
            "当摘要缺少历史细节时使用；可指定归档编号，也可在全部归档中搜索。"
        ),
    )
