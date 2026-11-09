"""工具注册表：管理可用工具并输出 OpenAI 兼容的 schema。"""

from __future__ import annotations

from typing import Any, Callable, Iterator

from core.tools.base import FunctionTool, Tool


class ToolRegistry:
    """按名称索引的工具集合。"""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._resources: list[Any] = []
        for item in tools or []:
            self.register(item)

    def add_resource(self, resource: Any) -> Any:
        """登记需要随注册表关闭的外部资源（例如 MCP 连接管理器）。"""
        close = getattr(resource, "close", None)
        if callable(close):
            self._resources.append(resource)
        return resource

    def close(self) -> None:
        """逆序关闭所有已登记资源；单个资源失败不会影响其他资源。"""
        for resource in reversed(self._resources):
            try:
                resource.close()
            except Exception:
                pass
        self._resources.clear()

    def register(self, item: Tool) -> Tool:
        if not isinstance(item, Tool):
            raise TypeError(f"注册的对象不是 Tool 实例：{type(item)!r}")
        self._tools[item.name] = item
        return item

    def tool(
        self,
        description: str | None = None,
        *,
        name: str | None = None,
    ) -> Callable[[Callable[..., Any]], FunctionTool]:
        """注册表级装饰器，等价于 tool(...) 但自动完成登记。"""

        def decorator(func: Callable[..., Any]) -> FunctionTool:
            instance = FunctionTool(func, name=name, description=description)
            self.register(instance)
            return instance

        return decorator

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [item.to_api_schema() for item in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())
