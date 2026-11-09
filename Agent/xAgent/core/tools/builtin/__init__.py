"""内置工具集合的装配入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.context.archive import ContextArchive, build_recall_tool
from core.tools.base import FunctionTool
from core.tools.builtin.datetime_tools import calculate, get_current_datetime, is_leap_year
from core.tools.builtin.agent_browser import build_agent_browser_tools
from core.tools.builtin.file_tools import build_file_tools
from core.tools.builtin.search_tools import build_search_tools
from core.tools.registry import ToolRegistry
from core.workspace import Workspace

if TYPE_CHECKING:
    from core.config.settings import Settings

BUILTIN_DATE_TOOLS: tuple[FunctionTool, ...] = (is_leap_year, get_current_datetime, calculate)


def register_builtin_tools(
    registry: ToolRegistry,
    workspace: Workspace,
    *,
    settings: "Settings | None" = None,
    search_api_key: str | None = None,
    project_root: str | None = None,
    context_archive: ContextArchive | None = None,
) -> ToolRegistry:
    """把内置工具注册到注册表；提供搜索 API Key 时同时启用联网搜索。"""
    for item in BUILTIN_DATE_TOOLS:
        registry.register(item)

    file_settings = settings.file_tools if settings is not None else None
    for item in build_file_tools(
        workspace,
        max_content_length=(
            file_settings.max_content_length if file_settings is not None else 10_000
        ),
        text_sniff_size=(
            file_settings.text_sniff_size if file_settings is not None else 8192
        ),
    ):
        registry.register(item)

    browser_settings = settings.browser if settings is not None else None
    for item in build_agent_browser_tools(
        project_root or workspace.root,
        executable_path=(
            browser_settings.executable_path if browser_settings is not None else None
        ),
        screenshot_dir=(
            browser_settings.screenshot_dir if browser_settings is not None else None
        ),
        timeout=(browser_settings.timeout if browser_settings is not None else 120.0),
    ):
        registry.register(item)

    archive = context_archive or ContextArchive(project_root or workspace.root)
    registry.register(build_recall_tool(archive))

    key = search_api_key
    if key is None and settings is not None:
        key = settings.search.baidu_qianfan_api_key
    if key:
        search_settings = settings.search if settings is not None else None
        for item in build_search_tools(
            key,
            timeout=(search_settings.timeout if search_settings is not None else 20.0),
            endpoint=(
                search_settings.endpoint
                if search_settings is not None
                else "https://qianfan.baidubce.com/v2/ai_search/web_search"
            ),
            max_query_length=(
                search_settings.max_query_length if search_settings is not None else 72
            ),
            max_results=(
                search_settings.max_results if search_settings is not None else 50
            ),
            max_content_per_item=(
                search_settings.max_content_per_item
                if search_settings is not None
                else 300
            ),
            max_total_length=(
                search_settings.max_total_length if search_settings is not None else 6000
            ),
        ):
            registry.register(item)
    return registry


__all__ = [
    "BUILTIN_DATE_TOOLS",
    "build_file_tools",
    "build_agent_browser_tools",
    "build_search_tools",
    "register_builtin_tools",
]
