"""工具抽象：把普通 Python 函数包装为模型可调用的工具。"""

from __future__ import annotations

import inspect
import re
import types
import typing
from abc import ABC, abstractmethod
from typing import Any, Callable

_ARGS_HEADINGS = ("args:", "arguments:", "parameters:", "参数:", "参数说明:")
_END_HEADINGS = ("returns:", "return:", "raises:", "yields:", "返回:", "异常:")


def _json_type(annotation: Any) -> dict[str, Any]:
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is str:
        return {"type": "string"}
    if annotation is dict:
        return {"type": "object"}
    if annotation in (list, set, tuple, frozenset):
        return {"type": "array", "items": {"type": "string"}}
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [item for item in typing.get_args(annotation) if item is not type(None)]
        if len(args) == 1:
            return _json_type(args[0])
        return {"type": "object"}
    if origin in (list, set, tuple, frozenset):
        args = typing.get_args(annotation)
        items = _json_type(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": items}
    if origin is dict:
        return {"type": "object"}
    if isinstance(annotation, type) and issubclass(annotation, bool):
        return {"type": "boolean"}
    return {"type": "string"}


def _parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """从 docstring 中解析整体描述与参数说明。"""
    if not doc:
        return "", {}
    lines = [line.rstrip() for line in doc.strip().splitlines()]
    summary_lines: list[str] = []
    args: dict[str, str] = {}
    in_args = False
    summary_finished = False

    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered in _ARGS_HEADINGS:
            in_args = True
            continue
        if lowered in _END_HEADINGS:
            in_args = False
            continue
        if in_args:
            match = re.match(r"^(\*{0,2}\w+)\s*[:：]\s*(.+)$", stripped)
            if match:
                args[match.group(1).lstrip("*")] = match.group(2).strip()
            continue
        if not stripped:
            summary_finished = True
            continue
        if not summary_lines and not summary_finished:
            summary_lines.append(stripped)

    return " ".join(part for part in summary_lines if part).strip(), args


def _unwrap(func: Callable[..., Any]) -> Callable[..., Any]:
    """展开 partial / method，拿到原始函数用于读取注解与文档。"""
    target = func
    seen = 0
    while hasattr(target, "func") and seen < 8:
        target = target.func
        seen += 1
    if inspect.ismethod(target):
        target = target.__func__
    return target


def _build_parameters(func: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(func)
    origin = _unwrap(func)
    try:
        hints = typing.get_type_hints(origin)
    except Exception:
        hints = {}
    _, doc_args = _parse_docstring(origin.__doc__)

    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in signature.parameters.items():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        schema = _json_type(hints.get(name, str))
        if name in doc_args:
            schema["description"] = doc_args[name]
        properties[name] = schema
        if parameter.default is inspect.Parameter.empty:
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


class Tool(ABC):
    """工具基类。"""

    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """执行工具并返回文本结果。"""

    def to_api_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class FunctionTool(Tool):
    """由可调用对象构建的工具。"""

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self.func = func
        origin = _unwrap(func)
        self.name = name or getattr(func, "__name__", None) or origin.__name__
        parsed_description, _ = _parse_docstring(origin.__doc__)
        self.description = description or parsed_description or func.__name__
        self.parameters = parameters if parameters is not None else _build_parameters(func)

    def execute(self, **kwargs: Any) -> str:
        result = self.func(**kwargs)
        return result if isinstance(result, str) else str(result)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FunctionTool {self.name}>"


def tool(
    description: str | None = None,
    *,
    name: str | None = None,
) -> Callable[[Callable[..., Any]], FunctionTool]:
    """装饰器：把函数注册为模型可调用的工具。"""

    def decorator(func: Callable[..., Any]) -> FunctionTool:
        return FunctionTool(func, name=name, description=description)

    return decorator
