"""Application object construction and dependency wiring."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.agent.engine import AgentEngine
from core.agent.session import Session
from core.config.settings import Settings, load_settings
from core.context.archive import ContextArchive
from core.context.manager import ContextManager
from core.llm.openai_client import OpenAICompatibleClient
from core.skills.manager import SkillManager
from core.tools.builtin import register_builtin_tools
from core.tools.builtin.skill_tools import build_skill_tools
from core.tools.registry import ToolRegistry
from core.workspace import Workspace

if TYPE_CHECKING:
    from core.mcp.manager import MCPManager


def build_skill_manager(project_root: Path | str | None = None) -> SkillManager:
    return SkillManager(project_root or Path.cwd())


def build_registry(
    settings: Settings | None = None,
    workspace: Workspace | None = None,
    skill_manager: SkillManager | None = None,
    *,
    project_root: Path | str | None = None,
    mcp_config_path: Path | str | None = None,
    mcp_manager: MCPManager | None = None,
    connect_mcp: bool = True,
    context_archive: ContextArchive | None = None,
) -> ToolRegistry:
    """构建工具注册表，Skill 工具、内置工具与 MCP 工具共用同一个注册表。"""
    settings = settings or load_settings()
    # 兼容早期调用方式 build_registry(settings, skill_manager)。
    if isinstance(workspace, SkillManager):
        skill_manager, workspace = skill_manager or workspace, None
    root = Path(project_root or Path.cwd()).expanduser().resolve()
    manager = skill_manager or build_skill_manager(root)
    registry = ToolRegistry(build_skill_tools(manager))
    context_settings = settings.context
    archive = context_archive or ContextArchive(root, context_settings.archive_subdir)
    register_builtin_tools(
        registry,
        workspace or build_workspace(settings),
        search_api_key=settings.search.baidu_qianfan_api_key,
        project_root=root,
        context_archive=archive,
    )
    if connect_mcp:
        from core.mcp.manager import register_mcp_tools

        active = register_mcp_tools(
            registry,
            project_root=root,
            config_path=mcp_config_path,
            manager=mcp_manager,
        )
        registry.add_resource(active)
    return registry


def _compose_system_prompt(settings: Settings, manager: SkillManager) -> str:
    prompt = settings.system_prompt
    section = manager.prompt_section()
    return f"{prompt}\n\n{section}" if section else prompt


def build_session(
    settings: Settings | None = None,
    skill_manager: SkillManager | None = None,
    *,
    project_root: Path | str | None = None,
) -> Session:
    """构建会话，并把已发现 Skill 的元数据注入系统提示词。"""
    settings = settings or load_settings()
    manager = skill_manager or build_skill_manager()
    session = Session(system_prompt=_compose_system_prompt(settings, manager))
    root = Path(project_root or Path.cwd()).expanduser().resolve()
    agents_path = root / settings.sessions.agents_md_filename
    if settings.agents_md_enabled and agents_path.is_file():
        try:
            content = agents_path.read_text(encoding="utf-8")
            session.add_agents_instructions(content[: settings.sessions.agents_md_max_chars])
        except (OSError, UnicodeError):
            pass
    # Skill 创建后自动刷新当前会话的系统提示词，无需重启即可发现新 Skill。
    manager.add_listener(
        lambda: session.update_system_prompt(_compose_system_prompt(settings, manager))
    )
    return session


def build_client(settings: Settings | None = None) -> OpenAICompatibleClient:
    settings = settings or load_settings()
    return OpenAICompatibleClient(settings.llm)


def build_engine(
    settings: Settings | None = None,
    config_path: str | None = None,
    *,
    project_root: Path | str | None = None,
    mcp_config_path: Path | str | None = None,
    connect_mcp: bool = True,
) -> AgentEngine:
    settings = settings or load_settings(config_path)
    root = Path(project_root or Path.cwd()).expanduser().resolve()
    manager = build_skill_manager(root)
    workspace = build_workspace(settings)

    mcp_manager = None
    if connect_mcp and not settings.mcp.async_load:
        from core.mcp.manager import MCPManager

        mcp_manager = MCPManager(project_root=root, config_path=mcp_config_path)

    try:
        client = build_client(settings)
        context_archive = ContextArchive(root)
        registry = build_registry(
            settings,
            workspace,
            manager,
            project_root=root,
            mcp_config_path=mcp_config_path,
            mcp_manager=mcp_manager,
            connect_mcp=connect_mcp and not settings.mcp.async_load,
        context_archive=ContextArchive(root, settings.context.archive_subdir),
        )
        session = build_session(settings, manager, project_root=root)
        context_manager = ContextManager(
            archive=ContextArchive(root, settings.context.archive_subdir),
            model=settings.llm.model,
            context_window=settings.llm.context_window,
            threshold=settings.context.compact_threshold,
            default_window=settings.context.default_window,
            message_overhead=settings.context.message_overhead,
            archive_subdir=settings.context.archive_subdir,
        )
        return AgentEngine(
            client=client,
            registry=registry,
            session=session,
            max_iterations=settings.llm.max_iterations,
            stream_enabled=settings.llm.stream,
            mcp_manager=mcp_manager,
            project_root=root,
            context_manager=context_manager,
        )
    except BaseException:
        if mcp_manager is not None:
            try:
                mcp_manager.close()
            except Exception:
                pass
        raise


def build_workspace(settings: Settings | None = None) -> Workspace:
    settings = settings or load_settings()
    return Workspace.from_root(settings.workspace.root, read_only=settings.workspace.read_only)
