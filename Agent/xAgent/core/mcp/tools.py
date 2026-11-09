"""把 MCP 工具包装成 xAgent 的 ``Tool``。"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from core.exceptions import MCPToolError, ToolError
from core.mcp.transport import MCPConnection
from core.tools.base import Tool

_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")
_MAX_TOOL_NAME_LENGTH = 64


def safe_tool_name(name: str, fallback: str = "mcp_tool") -> str:
    """生成符合 Function Calling 命名要求的工具名。"""
    cleaned = _INVALID_NAME_CHARS.sub("_", str(name or "")).strip("_")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"mcp_{cleaned}"
    return cleaned[:_MAX_TOOL_NAME_LENGTH]


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    """兼容 Pydantic 模型、字典以及 1.x / 2.x 的字段命名。"""
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
            continue
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


def _format_content_block(block: Any) -> str:
    kind = _get(block, "type")
    if kind == "text":
        return str(_get(block, "text", default="") or "")

    if kind == "image":
        mime = _get(block, "mimeType", "mime_type", default="未知类型")
        data = _get(block, "data", default="") or ""
        return f"[图片内容：{mime}，base64 长度 {len(str(data))}]"

    if kind == "audio":
        mime = _get(block, "mimeType", "mime_type", default="未知类型")
        data = _get(block, "data", default="") or ""
        return f"[音频内容：{mime}，base64 长度 {len(str(data))}]"

    if kind == "resource":
        resource = _get(block, "resource")
        if resource is None:
            return "[资源内容]"
        uri = _get(resource, "uri", default="")
        text = _get(resource, "text")
        if text is not None:
            return f"[资源 {uri}]\n{text}"
        mime = _get(resource, "mimeType", "mime_type", default="未知类型")
        blob = _get(resource, "blob", default="") or ""
        return f"[二进制资源 {uri}，类型 {mime}，base64 长度 {len(str(blob))}]"

    if kind == "resource_link":
        name = _get(block, "name", default="") or ""
        uri = _get(block, "uri", default="") or ""
        description = _get(block, "description", default="") or ""
        parts = ["[资源链接]", name, uri]
        if description:
            parts.append(description)
        return " ".join(part for part in parts if part)

    if kind:
        dumped = _get(block, "model_dump")
        if callable(dumped):
            try:
                return _json_text(dumped())
            except Exception:
                pass
        return f"[{kind} 内容]"
    return str(block)


def format_tool_result(result: Any) -> str:
    """把 ``CallToolResult`` 转成 LLM 易读的文本。"""
    parts: list[str] = []

    content = _get(result, "content")
    if content:
        for block in content:
            text = _format_content_block(block)
            if text:
                parts.append(text)

    structured = _get(result, "structuredContent", "structured_content")
    if structured is not None:
        structured_text = _json_text(structured)
        joined = "\n".join(parts)
        if structured_text not in joined:
            if parts:
                parts.append(f"结构化数据：\n{structured_text}")
            else:
                parts.append(structured_text)

    if not parts:
        return "MCP 工具已执行，未返回内容。"
    return "\n".join(parts)


def result_is_error(result: Any) -> bool:
    return bool(_get(result, "isError", "is_error", default=False))


def _normalize_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict) or not schema:
        return {"type": "object", "properties": {}}
    normalized = copy.deepcopy(schema)
    # 部分服务商不接受 JSON Schema 的 $schema 声明。
    normalized.pop("$schema", None)
    normalized.setdefault("type", "object")
    properties = normalized.get("properties")
    if properties is None:
        normalized["properties"] = {}
    elif not isinstance(properties, dict):
        normalized["properties"] = {}
    required = normalized.get("required")
    if required is not None:
        if isinstance(required, list):
            normalized["required"] = [item for item in required if isinstance(item, str)]
        else:
            normalized.pop("required", None)
    return normalized


class MCPTool(Tool):
    """一个远端 MCP 工具在本地注册表中的代理。"""

    def __init__(
        self,
        *,
        exposed_name: str,
        remote_name: str,
        server_name: str,
        description: str,
        parameters: dict[str, Any],
        connection: MCPConnection,
    ) -> None:
        self.name = exposed_name
        self.remote_name = remote_name
        self.server_name = server_name
        self.description = description or f"MCP Server「{server_name}」提供的工具：{remote_name}"
        self.parameters = _normalize_schema(parameters)
        self.connection = connection

    def execute(self, **kwargs: Any) -> str:
        try:
            result = self.connection.call_tool(self.remote_name, kwargs)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - 由引擎统一包装
            raise ToolError(
                f"MCP Server「{self.server_name}」工具「{self.remote_name}」调用失败："
                f"{type(exc).__name__}: {exc}"
            ) from exc

        text = format_tool_result(result)
        if result_is_error(result):
            raise MCPToolError(
                f"MCP Server「{self.server_name}」工具「{self.remote_name}」返回错误：{text}"
            )
        return text

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<MCPTool {self.server_name}/{self.remote_name} as {self.name}>"
        )


def build_mcp_tool(
    *,
    server_name: str,
    remote_tool: Any,
    exposed_name: str,
    connection: MCPConnection,
) -> MCPTool:
    remote_name = str(_get(remote_tool, "name", default="") or "")
    description = str(_get(remote_tool, "description", default="") or "")
    schema = _get(remote_tool, "inputSchema", "input_schema", default=None)
    return MCPTool(
        exposed_name=exposed_name,
        remote_name=remote_name,
        server_name=server_name,
        description=description,
        parameters=schema if isinstance(schema, dict) else {},
        connection=connection,
    )


# 兼容常见的内部调用写法。
format_call_result = format_tool_result


__all__ = [
    "MCPTool",
    "build_mcp_tool",
    "format_call_result",
    "format_tool_result",
    "result_is_error",
    "safe_tool_name",
]
