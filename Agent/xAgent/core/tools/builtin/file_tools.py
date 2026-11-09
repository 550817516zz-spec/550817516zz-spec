"""内置工具：工作区文件操作（受工作区沙箱约束）。"""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from core.tools.base import FunctionTool
from core.workspace import Workspace

MAX_CONTENT_LENGTH = 10000
TEXT_SNIFF_SIZE = 8192


def _is_text_file(path: Path, sniff_size: int = TEXT_SNIFF_SIZE) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(max(1, sniff_size))
    except OSError:
        return False
    return b"\x00" not in chunk


def build_file_tools(
    workspace: Workspace,
    *,
    max_content_length: int = MAX_CONTENT_LENGTH,
    text_sniff_size: int = TEXT_SNIFF_SIZE,
) -> list[FunctionTool]:
    """构建与文件相关的工具集合。"""

    def get_current_working_directory() -> str:
        """获取当前工作目录（工作区根目录）。"""
        return f"当前工作目录：{workspace.root_path}"

    def list_files_in_directory(directory: str | None = None) -> str:
        """列出指定目录下所有文件和子目录。

        Args:
            directory: 目标目录路径，默认为工作区根目录
        """
        try:
            path = workspace.resolve(directory)
        except Exception as exc:
            return f"列出目录文件失败：{exc}"
        if not path.exists():
            return f"目录不存在：{path}"
        if not path.is_dir():
            return f"指定路径不是目录：{path}"
        dirs: list[str] = []
        files: list[str] = []
        for entry in sorted(path.iterdir(), key=lambda item: item.name):
            if entry.is_dir():
                dirs.append(f"[DIR] {entry.name}")
            else:
                files.append(f"[FILE] {entry.name}")
        result = dirs + files
        if not result:
            return f"目录 {path} 为空。"
        return "\n".join(result)

    def get_file_type(file_path: str) -> str:
        """获取指定文件的类型信息。

        Args:
            file_path: 文件路径
        """
        try:
            path = workspace.resolve(file_path)
        except Exception as exc:
            return f"获取文件类型失败：{exc}"
        if not path.exists():
            return f"文件不存在：{path}"
        if path.is_dir():
            return f"指定路径是目录，不是文件：{path}"
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            return f"文件：{path}\n文件类型（MIME）：{mime_type}"
        extension = path.suffix
        if extension:
            return f"文件：{path}\n文件扩展名：{extension}\n无法推断 MIME 类型。"
        return f"文件：{path}\n无扩展名，无法推断文件类型。"

    def get_file_content(file_path: str) -> str:
        """获取指定文件的内容，仅支持纯文本文件。

        Args:
            file_path: 文件路径
        """
        try:
            path = workspace.resolve(file_path)
        except Exception as exc:
            return f"获取文件内容失败：{exc}"
        if not path.exists():
            return f"文件不存在：{path}"
        if path.is_dir():
            return f"指定路径是目录，不是文件：{path}"
        if not _is_text_file(path, text_sniff_size):
            return f"不支持读取非纯文本文件：{path}"
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"获取文件内容失败：{exc}"
        if len(content) > max_content_length:
            return content[:max_content_length] + f"\n\n[内容过长，已截断前 {max_content_length} 字符]"
        return content

    def create_file(directory: str | None, file_name: str) -> str:
        """创建新文件，目录不存在时自动创建。

        Args:
            directory: 目标目录路径，默认为工作区根目录
            file_name: 要创建的文件名
        """
        try:
            workspace.ensure_writable()
            if not file_name:
                return "请提供文件名。"
            base = workspace.resolve(directory)
            base.mkdir(parents=True, exist_ok=True)
            path = base / file_name
            if path.exists():
                return f"文件已存在：{path}"
            path.write_text("", encoding="utf-8")
        except Exception as exc:
            return f"创建文件失败：{exc}"
        return f"文件创建成功：{path}"

    def edit_file_content(file_path: str, content: str) -> str:
        """覆盖写入指定文件的内容，仅支持纯文本文件。

        Args:
            file_path: 文件路径
            content: 新的文件内容
        """
        try:
            workspace.ensure_writable()
            path = workspace.resolve(file_path)
            if not path.exists():
                return f"文件不存在：{path}"
            if path.is_dir():
                return f"指定路径是目录，不是文件：{path}"
            if not _is_text_file(path):
                return f"不支持编辑非纯文本文件：{path}"
            path.write_text(content, encoding="utf-8")
        except Exception as exc:
            return f"编辑文件失败：{exc}"
        return f"文件编辑成功：{path}"

    def create_directory(directory_path: str) -> str:
        """创建新目录，支持嵌套目录。

        Args:
            directory_path: 要创建的目录路径
        """
        try:
            workspace.ensure_writable()
            if not directory_path:
                return "请提供目录路径。"
            path = workspace.resolve(directory_path)
            if path.exists():
                if path.is_dir():
                    return f"目录已存在：{path}"
                return f"指定路径已存在且不是目录：{path}"
            path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return f"创建目录失败：{exc}"
        return f"目录创建成功：{path}"

    def delete_directory(directory_path: str) -> str:
        """删除目录，包括非空目录。

        Args:
            directory_path: 要删除的目录路径
        """
        try:
            workspace.ensure_writable()
            if not directory_path:
                return "请提供目录路径。"
            path = workspace.resolve(directory_path)
            if not path.exists():
                return f"目录不存在：{path}"
            if not path.is_dir():
                return f"指定路径不是目录：{path}"
            shutil.rmtree(path)
        except Exception as exc:
            return f"删除目录失败：{exc}"
        return f"目录删除成功（非空目录已删除）：{path}"

    def delete_file(file_path: str) -> str:
        """删除指定文件。

        Args:
            file_path: 要删除的文件路径
        """
        try:
            workspace.ensure_writable()
            if not file_path:
                return "请提供文件路径。"
            path = workspace.resolve(file_path)
            if not path.exists():
                return f"文件不存在：{path}"
            if path.is_dir():
                return f"指定路径是目录，请使用删除目录功能：{path}"
            path.unlink()
        except Exception as exc:
            return f"删除文件失败：{exc}"
        return f"文件删除成功：{path}"

    specs: list[tuple[str, str, object]] = [
        ("get_current_working_directory", "获取当前工作目录。", get_current_working_directory),
        ("list_files_in_directory", "列出指定目录下所有文件和子目录。", list_files_in_directory),
        ("get_file_type", "获取指定文件的文件类型（MIME 类型或扩展名）。", get_file_type),
        ("get_file_content", "获取指定文件的内容（仅支持纯文本格式文件）。", get_file_content),
        ("create_file", "根据指定的目录和文件名创建新文件（目录不存在时自动创建）。", create_file),
        ("edit_file_content", "编辑指定文件的内容（仅支持纯文本文件，会覆盖原内容）。", edit_file_content),
        ("create_directory", "创建新目录（支持嵌套目录）。", create_directory),
        ("delete_directory", "删除目录（非空目录也会被删除）。", delete_directory),
        ("delete_file", "删除文件。", delete_file),
    ]

    return [
        FunctionTool(func, name=name, description=description)
        for name, description, func in specs
    ]


__all__ = ["build_file_tools"]
