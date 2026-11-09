"""对话主界面。"""

from __future__ import annotations

import asyncio
from pathlib import Path
import uuid

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from core.agent.engine import AgentEngine
from core.agent.events import (
    AssistantDeltaEvent,
    CompactionFinishedEvent,
    CompactionStartedEvent,
    ContextStatusEvent,
    ContextWarningEvent,
    DoneEvent,
    ErrorEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from tui.widgets.message_block import MessageBlock
from tui.widgets.message_log import MessageLog, truncate
from tui.widgets.prompt_input import PromptInput
from tui.widgets.status_bar import StatusBar
from tui.widgets.top_bar import TopBar
from tui.widgets.info_bar import InfoBar
from tui.widgets.sidebar import Sidebar
from tui.widgets.tool_card import ToolCallCard
from tui.widgets.bottom_bar import BottomStatusBar
from tui.widgets.command_input import CommandInput
from tui.modals.help_modal import HelpModal
from tui.modals.compaction_modal import CompactionModal
from tui.modals.session_modal import SessionModal
from tui.widgets.command_suggestions import CommandSuggestions
from core.agent.session_store import SessionStore

HELP_TEXT = """可用命令：
/help      显示帮助
/compact   压缩上下文并归档原始记录
/clear     清空对话历史
/tools     查看已注册的工具
/doctor    运行连通性诊断
/history   查看当前消息条数
exit       退出程序"""


class ChatScreen(Screen):
    """承载对话流的界面。"""

    AUTO_FOCUS = "#command-input"

    BINDINGS = [
        Binding("ctrl+l", "clear_chat", "清空对话"),
        Binding("f1", "show_help", "帮助"),
        Binding("escape", "interrupt", "中断生成"),
        Binding("ctrl+b", "toggle_sidebar", "侧栏"),
        Binding("ctrl+n", "new_session", "新会话"),
        Binding("ctrl+q", "quit_app", "退出"),
    ]

    COMMANDS = ["/help", "/compact", "/clear", "/new", "/resume", "/save",
                "/tools", "/history", "/cwd", "/model", "/doctor", "/quit"]

    def __init__(self, engine: AgentEngine, workspace: Path | None = None) -> None:
        super().__init__()
        self.engine = engine
        self.workspace = workspace or Path.cwd()
        self._streaming_block: MessageBlock | None = None
        self._streaming_buffer = ""
        self._tool_cards: dict[str, ToolCallCard] = {}
        self._busy = False
        client_settings = getattr(engine.client, "settings", None)
        session_settings = getattr(client_settings, "sessions", None)
        self.session_store = SessionStore(
            Path(getattr(engine, "project_root", None) or Path.cwd()),
            getattr(session_settings, "directory", ".agents/sessions"),
            getattr(session_settings, "export_dir", ".agents/exports"),
            getattr(session_settings, "event_log", True),
        )
        existing = self.session_store.list_sessions(1)
        self._session_id = existing[0]["id"] if existing else SessionStore.new_id()
        self._session_title = "新会话"
        self._rounds = 0
        self._tool_calls_total = 0
        self._last_turn_tool_calls = 0

    def compose(self) -> ComposeResult:
        yield TopBar(app_name="xAgent", model=getattr(self.engine.client, "model", ""), workspace=self.workspace)
        yield InfoBar(app_name="xAgent", tool_count=len(self.engine.registry), model=getattr(self.engine.client, "model", ""), workspace=self.workspace)
        with Horizontal(id="main-row"):
            with Vertical(id="chat-col"):
                yield MessageLog(id="messages")
                yield CommandSuggestions()
                yield CommandInput()
            yield Sidebar(
                model=getattr(self.engine.client, "model", ""),
                base_url=getattr(self.engine.client, "settings", None)
                    and getattr(self.engine.client.settings, "base_url", "")
                    or "",
                workspace=self.workspace,
                tool_names=self.engine.tool_names,
            )
        yield BottomStatusBar()

    async def on_mount(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.update_session(session_id=self._session_id, rounds=self._rounds, msg_count=len(self.engine.session.messages), status="就绪")
        bottom = self.query_one(BottomStatusBar)
        bottom.reset()
        self._refresh_context()
        log = self.query_one(MessageLog)
        await log.append_notice(
            "xAgent 已就绪。输入消息开始对话，可使用 /help 查看内置命令。"
        )
        for line in self.engine.mcp_status_lines():
            await log.append_notice(line)
        for message in self.engine.mcp_errors:
            await log.append_error(message)
        saved = None
        if self.session_store.directory.joinpath(f"{self._session_id}.json").is_file():
            self._load_event_log()
            try:
                saved, self._session_title = self.session_store.load(self._session_id)
                self.engine.session = saved
            except Exception:
                pass
        await self._replay_on_mount_events()
        self._save_session()
        if getattr(self.engine, "mcp_manager", None) is not None:
            self.run_worker(self._load_mcp_background(), group="mcp", exclusive=True)
        try:
            self.query_one("#command-input").focus()
        except Exception:
            pass

    async def on_command_input_submitted(self, event: CommandInput.Submitted) -> None:
        text = event.value
        event.input.clear()
        if not text:
            return
        if text.lower() in ("exit", "quit", "q"):
            self.app.exit()
            return
        if text.startswith("/"):
            await self._handle_command(text)
            return
        if self.engine.context.requires_compaction:
            await self.query_one(MessageLog).append_error(
                "当前上下文已达到压缩阈值，暂时不能接受新的提示词。"
                "请先执行 /compact 完成上下文压缩。"
            )
            self._refresh_context()
            return
        self.run_worker(self._run_agent(text), group="agent", exclusive=True)

    async def on_command_input_changed(self, event: CommandInput.Changed) -> None:
        self.query_one(CommandSuggestions).update_query(event.value)

    async def _handle_command(self, text: str) -> None:
        log = self.query_one(MessageLog)
        command = text.split(maxsplit=1)[0].lower()
        if command == "/help":
            try:
                await self.app.push_screen(HelpModal())
            except Exception:
                pass
            return
        if command == "/compact":
            if self._busy:
                await log.append_error("当前正在执行任务，请稍后再执行 /compact。")
                return
            self.run_worker(self._run_compaction(), group="agent", exclusive=True)
            return
        if command == "/clear":
            self.engine.reset_session()
            await log.clear()
            await log.append_notice("对话历史已清空。")
            self._refresh_context()
            self._update_sidebar()
            return
        if command == "/new":
            await self._new_session()
            return
        if command == "/save":
            self._save_session()
            await log.append_notice(f"会话已保存：{self._session_id}")
            return
        if command == "/resume":
            await self._resume_session()
            return
        if command == "/tools":
            names = self.engine.tool_names
            await log.append_notice(f"已注册工具（{len(names)}）：{', '.join(names)}")
            return
        if command == "/history":
            await log.append_notice(f"当前会话共有 {len(self.engine.session.messages)} 条消息。")
            return
        if command == "/cwd":
            await log.append_notice(f"工作目录：{self.workspace}")
            return
        if command == "/model":
            await log.append_notice(f"模型：{getattr(self.engine.client, 'model', '')}")
            return
        if command == "/doctor":
            await self._run_diagnostics()
            return
        if command == "/quit":
            self.app.exit()
            return
        await log.append_error(f"未知命令：{command}，输入 /help 查看帮助。")

    def _save_session(self) -> None:
        self.session_store.save(self._session_id, self.engine.session, self._session_title)

    def _record_event(self, kind: str, **payload: object) -> None:
        self.session_store.append_event(
            self._session_id,
            {"time": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
             "type": kind, **payload},
        )

    async def _new_session(self) -> None:
        if self._busy:
            return
        self._save_session()
        self.engine.reset_session()
        self._session_id = SessionStore.new_id()
        self._session_title = "新会话"
        self._rounds = self._tool_calls_total = 0
        log = self.query_one(MessageLog)
        await log.clear()
        await log.append_notice("已新建会话；上一会话已自动保存。")
        self._save_session()
        self._refresh_context()
        self._update_sidebar()

    async def _resume_session(self) -> None:
        settings = getattr(self.engine.client, "settings", None)
        limit = getattr(getattr(settings, "sessions", None), "list_limit", 30)
        sessions = self.session_store.list_sessions(limit)
        if not sessions:
            await self.query_one(MessageLog).append_notice("没有找到已保存的会话。")
            return
        selected = await self.app.push_screen_wait(SessionModal(sessions))
        if not selected:
            return
        try:
            session, title = self.session_store.load(selected)
        except Exception as exc:
            await self.query_one(MessageLog).append_error(f"恢复会话失败：{exc}")
            return
        self._save_session()
        self.engine.session = session
        self.session_store.replay(selected)
        self._session_id = selected
        self._session_title = title
        self._rounds = self._tool_calls_total = 0
        self.engine.context.reset_after_compaction()
        await self.query_one(MessageLog).clear()
        await self.query_one(MessageLog).append_notice(f"已恢复会话：{title or selected}")
        await self._replay_events(self.session_store.replay(selected))
        self._refresh_context()
        self._update_sidebar()

    async def _replay_events(self, events: list[dict]) -> None:
        log = self.query_one(MessageLog)
        for item in events:
            event_type = item.get("type")
            if event_type == "user":
                await log.append_user(str(item.get("text", "")))
            elif event_type == "assistant":
                await log.append_assistant(str(item.get("text", "")))
            elif event_type == "tool_result":
                await log.append_notice(f"工具 {item.get('name', '')}：{item.get('result', '')}")

    def _load_event_log(self) -> None:
        self._replay_on_mount = self.session_store.replay(self._session_id)

    async def _replay_on_mount_events(self) -> None:
        events = getattr(self, "_replay_on_mount", [])
        if events:
            await self._replay_events(events)

    async def _load_mcp_background(self) -> None:
        await self.query_one(MessageLog).append_notice("正在后台加载 MCP Server…")
        lines = await asyncio.to_thread(self.engine.load_mcp)
        for line in lines:
            if "失败" in line or "错误" in line:
                await self.query_one(MessageLog).append_error(line)
            else:
                await self.query_one(MessageLog).append_notice(line)
        self.query_one(Sidebar).update_tools(self.engine.tool_names, self.engine.mcp_status_lines())
        self.query_one(InfoBar).update_meta(tool_count=len(self.engine.registry))

    async def _run_diagnostics(self) -> None:
        """执行连通性诊断并输出报告。"""
        log = self.query_one(MessageLog)
        await log.append_notice("正在运行诊断…")
        try:
            from core.llm.diagnostics import run_diagnostics

            # 从客户端获取 settings
            settings = getattr(self.engine.client, "settings", None)
            if settings is None:
                await log.append_error("无法获取模型配置，诊断中止。")
                return
            report = await run_diagnostics(settings)
            for line in report.summary().splitlines():
                await log.append_notice(line)
        except Exception as exc:
            await log.append_error(f"诊断异常：{type(exc).__name__}: {exc}")

    async def _run_agent(self, text: str) -> None:
        if self._busy:
            return
        self._set_busy(True)
        log = self.query_one(MessageLog)
        bottom = self.query_one(BottomStatusBar)
        sidebar = self.query_one(Sidebar)
        bottom.start_round()
        self._streaming_block = None
        self._streaming_buffer = ""
        self._tool_cards.clear()
        self._last_turn_tool_calls = 0

        try:
            async for event in self.engine.run(text):
                if isinstance(event, UserMessageEvent):
                    await log.append_user(event.text)
                    self._record_event("user", text=event.text)
                    self._session_title = self._session_title if self._rounds else event.text[:48]
                    self._save_session()
                    self._update_sidebar()
                elif isinstance(event, AssistantDeltaEvent):
                    if self._streaming_block is None:
                        self._streaming_block = await log.append_assistant()
                    self._streaming_buffer += event.delta
                    self._streaming_block.update_body(self._streaming_buffer)
                    self._save_session()
                elif isinstance(event, ToolCallEvent):
                    self._record_event("tool_call", call_id=event.call_id, name=event.name,
                                       arguments=event.arguments)
                    card = ToolCallCard(event.name, event.arguments)
                    await log.mount(card)
                    log.scroll_end(animate=False)
                    self._tool_cards[event.call_id] = card
                    self._last_turn_tool_calls += 1
                    self._tool_calls_total += 1
                    bottom.add_tool_call()
                    self._update_sidebar()
                elif isinstance(event, ToolResultEvent):
                    self._record_event("tool_result", call_id=event.call_id, name=event.name,
                                       result=event.result, ok=event.ok)
                    card = self._tool_cards.pop(event.call_id, None)
                    if card is not None:
                        card.set_result(event.result, ok=event.ok)
                    self._update_sidebar()
                elif isinstance(event, ContextStatusEvent):
                    self._show_context(event)
                elif isinstance(event, ContextWarningEvent):
                    await log.append_error(event.message)
                    self._refresh_context()
                elif isinstance(event, CompactionStartedEvent):
                    if event.message:
                        await log.append_notice(event.message)
                elif isinstance(event, CompactionFinishedEvent):
                    await self._show_compaction_result(event)
                elif isinstance(event, ErrorEvent):
                    await log.append_error(event.message)
                elif isinstance(event, DoneEvent):
                    self._save_session()
                    self._record_event("assistant", text=self._streaming_buffer or event.text)
                    self._rounds += 1
                    bottom.end_round(model=getattr(self.engine.client, "model", ""))
                    self._update_sidebar()
                    self._refresh_context()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                log = self.query_one(MessageLog)
                await log.append_error(f"界面处理异常：{type(exc).__name__}: {exc}")
            except Exception:
                pass
            self._rounds += 1
            try:
                bottom.end_round(model=getattr(self.engine.client, "model", ""))
            except Exception:
                pass
            self._update_sidebar()
        finally:
            self._streaming_block = None
            self._streaming_buffer = ""
            self._tool_cards.clear()
            self._set_busy(False)
            self._update_sidebar()
            try:
                self.query_one("#command-input").focus()
            except Exception:
                pass

    async def _run_compaction(self) -> None:
        """执行 /compact：只允许 LLM 生成摘要，不执行其他工具。"""
        if self._busy:
            return
        self._set_busy(True)
        log = self.query_one(MessageLog)
        try:
            async for event in self.engine.compact():
                if isinstance(event, CompactionStartedEvent):
                    if event.message:
                        await log.append_notice(event.message)
                elif isinstance(event, CompactionFinishedEvent):
                    await self._show_compaction_result(event)
                elif isinstance(event, ContextStatusEvent):
                    self._show_context(event)
                elif isinstance(event, ContextWarningEvent):
                    await log.append_error(event.message)
                elif isinstance(event, ErrorEvent):
                    await log.append_error(event.message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                await log.append_error(f"压缩界面处理异常：{type(exc).__name__}: {exc}")
            except Exception:
                pass
        finally:
            self._set_busy(False)
            self._refresh_context()
            self._update_sidebar()
            try:
                self.query_one("#command-input").focus()
            except Exception:
                pass

    async def _show_compaction_result(self, event: CompactionFinishedEvent) -> None:
        """压缩成功后展示双栏对照浮层。"""
        log = self.query_one(MessageLog)
        if event.message:
            await log.append_notice(event.message)
        self._refresh_context()
        if not (event.original_text or event.summary_text):
            return
        try:
            await self.app.push_screen(
                CompactionModal(
                    original_text=event.original_text,
                    summary_text=event.summary_text,
                    archive_id=event.archive_id,
                    summary_tokens=event.summary_tokens,
                )
            )
        except Exception as exc:
            await log.append_error(f"无法打开压缩详情面板：{type(exc).__name__}: {exc}")

    def _show_context(self, stats: object) -> None:
        """把上下文占用写到顶部信息条。"""
        try:
            info = self.query_one(InfoBar)
            info.update_context(
                int(getattr(stats, "used_tokens", 0)),
                int(getattr(stats, "window_tokens", 0)),
                float(getattr(stats, "percent", 0.0)),
                window_is_default=bool(getattr(stats, "window_is_default", False)),
                compact_required=bool(getattr(stats, "compact_required", False)),
                from_api=bool(getattr(stats, "from_api", False)),
            )
        except Exception:  # pragma: no cover
            pass

    def _refresh_context(self) -> None:
        try:
            self._show_context(self.engine.context_stats())
        except Exception:  # pragma: no cover
            pass

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        try:
            self.query_one("#command-input").disabled = busy
        except Exception:  # pragma: no cover
            pass

    def _update_sidebar(self) -> None:
        try:
            sidebar = self.query_one(Sidebar)
            self._rounds += 0
            sidebar.update_session(
                session_id=self._session_id,
                rounds=self._rounds,
                msg_count=len(self.engine.session.messages),
                status="思考中" if self._busy else "就绪",
                tool_calls=self._tool_calls_total,
            )
        except Exception:  # pragma: no cover
            pass

    def action_interrupt(self) -> None:
        if self._busy:
            bottom = self.query_one(BottomStatusBar)
            bottom.end_round(model=getattr(self.engine.client, "model", ""))
            self._set_busy(False)

    def action_toggle_sidebar(self) -> None:
        try:
            sidebar = self.query_one(Sidebar)
            sidebar.display = not sidebar.display
        except Exception:  # pragma: no cover
            pass

    def action_new_session(self) -> None:
        self.engine.reset_session()
        self._session_id = uuid.uuid4().hex[:8]
        self._rounds = 0
        self._tool_calls_total = 0
        self.run_worker(self._clear_log(), exclusive=True)
        bottom = self.query_one(BottomStatusBar)
        bottom.reset()
        self._refresh_context()
        self._update_sidebar()

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_clear_chat(self) -> None:
        self.engine.reset_session()
        self._rounds = 0
        self._tool_calls_total = 0
        self.run_worker(self._clear_log(), exclusive=True)
        bottom = self.query_one(BottomStatusBar)
        bottom.reset()
        self._refresh_context()
        self._update_sidebar()

    def action_show_help(self) -> None:
        self.run_worker(self._push_help(), exclusive=True)

    async def _push_help(self) -> None:
        await self.app.push_screen(HelpModal())
