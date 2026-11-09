"""右侧会话信息面板。"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Static


TOOL_DESCS: dict[str, str] = {
    "isLeapYear": "判断指定年份是否为闰年，返回判断结果及依据（用本地 Python 计算）",
    "get_current_datetime": "获取当前电脑的日期和时间（通过执行本地逻辑获得）",
    "calculate": "计算简单的四则运算表达式",
    "get_current_working_directory": "获取当前工作目录（也是所有文件工具允许访问的根目录）",
    "list_files_in_directory": "列出指定目录下的所有文件和子目录（不递归）",
    "get_file_type": "获取指定文件的类型：扩展名、MIME 类型、是否为纯文本",
    "get_file_content": "读取指定纯文本文件的完整内容（UTF-8），二进制文件不支持读取",
    "create_file": "在指定目录下按文件名新建一个纯文本文件；文件已存在时报错，不会覆盖",
    "edit_file_content": "编辑已存在的纯文本文件，整体覆盖原内容",
    "create_directory": "创建新目录（支持嵌套目录）",
    "delete_directory": "删除目录（非空目录也会被删除）",
    "delete_file": "删除文件",
    "recallContext": "检索上下文压缩时归档的原始对话（可指定归档编号）",
}


class Sidebar(Vertical):
    """右侧会话与工具面板。"""

    def __init__(self, model: str = "", base_url: str = "", workspace: Path | None = None, tool_names: list[str] | None = None, **kwargs) -> None:
        kwargs.setdefault("id", "sidebar")
        super().__init__(classes="sidebar", **kwargs)
        self.model = model
        self.base_url = base_url
        self.workspace = workspace or Path.cwd()
        self.tool_names = tool_names or []
        self.session_id = ""
        self.rounds = 0
        self.msg_count = 0
        self.max_iters = 8
        self.status = "就绪"
        self.tool_calls = 0
        self.elapsed = 0.0
        self.mcp_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Label("会话", classes="sidebar-title")
        yield Vertical(
            Static("", classes="sidebar-row"),
            classes="sidebar-section",
            id="session-section",
        )
        yield Label("工具", classes="sidebar-title")
        yield VerticalScroll(id="mcp-section")
        yield Label("本地工具", classes="sidebar-title")
        yield VerticalScroll(id="tools-section")

    def on_mount(self) -> None:
        self._render_session()
        self._render_tools()

    def update_session(self, session_id: str = "", rounds: int = 0, msg_count: int = 0, status: str = "就绪", tool_calls: int = 0, elapsed: float = 0.0) -> None:
        self.session_id = session_id
        self.rounds = rounds
        self.msg_count = msg_count
        self.status = status
        self.tool_calls = tool_calls
        self.elapsed = elapsed
        self._render_session()

    def _render_session(self) -> None:
        section = self.query_one("#session-section", Vertical)
        section.remove_children()
        cwd = str(self.workspace)
        if len(cwd) > 26:
            cwd = "…" + cwd[-23:]
        rows = [
            ("模型", self.model),
            ("接口", self.base_url),
            ("目录", cwd),
            ("会话", self.session_id[:8] if self.session_id else "-"),
            ("轮次", str(self.rounds)),
            ("消息", str(self.msg_count)),
            ("上限", f"{self.max_iters} 次模型调用/轮"),
            ("状态", self.status),
        ]
        for key, value in rows:
            section.mount(Static(f"[b]{key}[/b]  {value}", classes="sidebar-row", markup=True))

    def _render_tools(self) -> None:
        section = self.query_one("#tools-section", VerticalScroll)
        section.remove_children()
        section.mount(Static(f"[b]工具 · {len(self.tool_names)}[/b]", classes="sidebar-subtitle", markup=True))
        for name in self.tool_names:
            desc = TOOL_DESCS.get(name, "")
            section.mount(
                Static(f"[b]{name}[/b] — [dim]{desc}[/dim]", classes="sidebar-tool", markup=True)
            )

    def update_tools(self, tool_names: list[str], mcp_lines: list[str]) -> None:
        self.tool_names = list(tool_names)
        self.mcp_lines = list(mcp_lines)
        mcp = self.query_one("#mcp-section", VerticalScroll)
        mcp.remove_children()
        mcp.mount(Static(f"[b]MCP · {len(mcp_lines)}[/b]", classes="sidebar-subtitle", markup=True))
        for line in mcp_lines:
            mcp.mount(Static(line, classes="sidebar-tool"))
        self._render_tools()
