"""帮助弹窗。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class HelpModal(ModalScreen[None]):
    """居中的帮助弹窗。"""

    BINDINGS = [("escape", "dismiss", "关闭")]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("xAgent 帮助", classes="help-title"),
            Label("使用方法", classes="help-section-title"),
            Static("在底部输入框输入问题，Enter 发送，Shift+Enter（或 Ctrl+J）换行。", classes="help-text"),
            Static("模型需要查看/修改文件时会自动调用工具，工具卡片可点击展开。", classes="help-text"),
            Static("Esc 中断当前生成；已完成的问答才会写入历史。", classes="help-text"),
            Static("上下文达到窗口 70% 后会暂停新提示词，请用 /compact 压缩并归档历史。", classes="help-text"),
            Label("命令", classes="help-section-title"),
            Static("[b]/help[/b]　打开本帮助", classes="help-cmd", markup=True),
            Static("[b]/compact[/b]　压缩上下文，原始记录归档到 .agents/context/", classes="help-cmd", markup=True),
            Static("[b]/clear[/b]　清空界面（保留历史）", classes="help-cmd", markup=True),
            Static("[b]/new[/b]　新建会话（重置历史）", classes="help-cmd", markup=True),
            Static("[b]/tools[/b]　列出已注册工具", classes="help-cmd", markup=True),
            Static("[b]/history[/b]　查看当前消息条数", classes="help-cmd", markup=True),
            Static("[b]/cwd[/b]　显示工作目录", classes="help-cmd", markup=True),
            Static("[b]/model[/b]　显示模型与接口", classes="help-cmd", markup=True),
            Static("[b]/doctor[/b]　运行连通性诊断", classes="help-cmd", markup=True),
            Static("[b]/quit[/b]　退出", classes="help-cmd", markup=True),
            Label("快捷键", classes="help-section-title"),
            Static("^q 退出　^l 清屏　^n 新会话　^b 侧栏　f1 帮助　Esc 中断　^p palette", classes="help-text"),
            classes="help-dialog",
        )

    def action_dismiss(self) -> None:
        self.dismiss()
