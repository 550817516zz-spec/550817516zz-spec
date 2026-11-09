"""工作区：限制文件工具的可访问范围。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.exceptions import ToolError


@dataclass(frozen=True, slots=True)
class Workspace:
    """文件操作的根目录沙箱。"""

    root: Path
    read_only: bool = False

    @classmethod
    def from_root(cls, root: str | Path | None = None, *, read_only: bool = False) -> "Workspace":
        base = Path(root).expanduser() if root else Path.cwd()
        return cls(root=base.resolve(), read_only=read_only)

    @property
    def root_path(self) -> Path:
        return self.root

    def resolve(self, path: str | Path | None) -> Path:
        """解析相对路径并校验是否越界。"""
        candidate = Path(path).expanduser() if path else Path(".")
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise ToolError(f"路径超出工作区范围（{self.root}）：{path}")
        return resolved

    def ensure_writable(self) -> None:
        if self.read_only:
            raise ToolError("当前工作区为只读模式，禁止执行写操作。")
