"""Inline slash-command completion guide."""
from textual.widgets import Static


class CommandSuggestions(Static):
    COMMANDS = (
        ("/new", "新建会话并保存当前会话"), ("/resume", "恢复历史会话"),
        ("/save", "保存当前会话"), ("/compact", "压缩并归档上下文"),
        ("/clear", "清空当前会话"), ("/history", "查看当前消息数"),
        ("/tools", "列出可用工具"), ("/model", "显示模型"),
        ("/cwd", "显示工作目录"), ("/doctor", "运行连接诊断"),
        ("/help", "显示帮助"), ("/quit", "退出"),
    )

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "command-suggestions")
        kwargs.setdefault("classes", "command-suggestions")
        super().__init__("", **kwargs)

    def update_query(self, value: str, limit: int = 8) -> None:
        if not value.startswith("/") or " " in value:
            self.display = False
            return
        matches = [(name, desc) for name, desc in self.COMMANDS if name.startswith(value.lower())]
        self.update("\n".join(f"[b]{name}[/b]  {desc}" for name, desc in matches[:limit]) or "无匹配命令")
        self.display = True
