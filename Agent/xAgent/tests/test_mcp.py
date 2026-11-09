"""MCP 客户端单元测试（不需要真实网络）。"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.exceptions import MCPConfigError, MCPToolError
from core.mcp.config import (
    load_mcp_servers,
    mcp_disabled,
    resolve_mcp_config_path,
)
from core.mcp.manager import MCPManager
from core.mcp.tools import (
    MCPTool,
    format_tool_result,
    result_is_error,
    safe_tool_name,
)
from core.tools.base import FunctionTool
from core.tools.registry import ToolRegistry


class MCPConfigTest(unittest.TestCase):
    def test_loads_streamable_http_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "demo": {
                                "type": "streamable_http",
                                "url": "https://example.com/mcp",
                                "headers": {"Authorization": "Bearer token"},
                                "timeout": 12,
                            },
                            "alias": {
                                "type": "http",
                                "url": "https://example.com/other",
                            },
                            "disabled": {"url": "https://example.com/x", "enabled": False},
                        }
                    }
                ),
                encoding="utf-8",
            )
            configs, errors = load_mcp_servers(path)

        self.assertEqual(errors, [])
        self.assertEqual([item.name for item in configs], ["demo", "alias"])
        self.assertEqual(configs[0].url, "https://example.com/mcp")
        self.assertEqual(configs[0].headers["Authorization"], "Bearer token")
        self.assertEqual(configs[0].timeout, 12)
        self.assertEqual(configs[1].server_type, "streamable_http")

    def test_one_invalid_server_does_not_block_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "bad": {"type": "stdio", "command": "python"},
                            "no-url": {"type": "streamable_http"},
                            "good": {"url": "https://example.com/mcp"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            configs, errors = load_mcp_servers(path)

        self.assertEqual([item.name for item in configs], ["good"])
        self.assertEqual(len(errors), 2)
        self.assertIn("stdio", errors[0])
        self.assertIn("url", errors[1])

    def test_malformed_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".mcp.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(MCPConfigError):
                load_mcp_servers(path)

    def test_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_mcp_servers(Path(tmp) / "missing.json"), ([], []))

    def test_resolves_project_directory_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"XAGENT_MCP_CONFIG": ""}):
                self.assertEqual(
                    resolve_mcp_config_path(tmp),
                    (Path(tmp) / ".mcp.json").resolve(),
                )
            with patch.dict("os.environ", {"XAGENT_MCP_CONFIG": str(Path(tmp) / "x.json")}):
                self.assertEqual(resolve_mcp_config_path(tmp), (Path(tmp) / "x.json").resolve())

    def test_disable_flag(self) -> None:
        with patch.dict("os.environ", {"XAGENT_MCP_DISABLED": "true"}):
            self.assertTrue(mcp_disabled())
        with patch.dict("os.environ", {"XAGENT_MCP_DISABLED": "0"}):
            self.assertFalse(mcp_disabled())


class FakeConnection:
    def __init__(self, name: str, result=None, error: Exception | None = None) -> None:
        self.name = name
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict]] = []
        self.connected = True

    def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, dict(arguments)))
        if self.error is not None:
            raise self.error
        return self.result


def remote_tool(name: str, description: str = "", schema=None):
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema=schema or {"type": "object", "properties": {}},
    )


class MCPToolRegistrationTest(unittest.TestCase):
    def test_tools_are_registered_and_conflicts_use_server_prefix(self) -> None:
        registry = ToolRegistry()
        registry.register(
            FunctionTool(
                lambda: "local",
                name="echo",
                description="本地 echo",
                parameters={"type": "object", "properties": {}},
            )
        )
        manager = MCPManager(project_root=Path.cwd())
        server_a = FakeConnection("Server A")
        server_b = FakeConnection("Server-B")
        manager._remote_tools = [
            (server_a, remote_tool("echo")),
            (server_a, remote_tool("only-a")),
            (server_b, remote_tool("only-a")),
        ]

        manager.register_tools(registry)

        self.assertIn("Server_A_echo", registry.names())
        self.assertIn("only-a", registry.names())
        self.assertIn("Server-B_only-a", registry.names())
        self.assertEqual(manager.resolve_tool("Server_A_echo"), ("Server A", "echo"))
        self.assertEqual(
            manager.resolve_tool("Server-B_only-a"), ("Server-B", "only-a")
        )
        self.assertEqual(
            manager.server_tool_map["Server A"]["echo"], "Server_A_echo"
        )
        # 与本地工具共存，且注册表仍然只包含唯一名称。
        self.assertEqual(registry.names().count("Server_A_echo"), 1)
        self.assertEqual(registry.get("echo").description, "本地 echo")

    def test_schema_is_normalized_and_description_preserved(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(project_root=Path.cwd())
        manager._remote_tools = [
            (
                FakeConnection("demo"),
                remote_tool(
                    "lookup",
                    "查询信息",
                    {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                        "required": ["q"],
                    },
                ),
            )
        ]
        manager.register_tools(registry)
        tool = registry.get("lookup")
        self.assertIsInstance(tool, MCPTool)
        self.assertEqual(tool.description, "查询信息")
        self.assertNotIn("$schema", tool.parameters)
        self.assertEqual(tool.to_api_schema()["function"]["name"], "lookup")

    def test_long_and_invalid_names_are_sanitized(self) -> None:
        self.assertEqual(safe_tool_name("中文工具"), "mcp_tool")
        self.assertEqual(safe_tool_name("1 tool"), "mcp_1_tool")
        self.assertEqual(len(safe_tool_name("x" * 100)), 64)


class MCPResultFormatTest(unittest.TestCase):
    def test_text_and_structured_content_are_both_returned(self) -> None:
        result = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello")],
            structuredContent={"answer": 42},
            isError=False,
        )
        text = format_tool_result(result)
        self.assertIn("hello", text)
        self.assertIn("结构化数据", text)
        self.assertIn('"answer": 42', text)

    def test_resource_and_link_blocks(self) -> None:
        result = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="resource",
                    resource=SimpleNamespace(uri="file:///a.txt", text="body"),
                ),
                SimpleNamespace(
                    type="resource_link",
                    name="doc",
                    uri="https://example.com/doc",
                    description="说明",
                ),
                SimpleNamespace(type="image", mimeType="image/png", data="AAAA"),
            ],
            isError=False,
        )
        text = format_tool_result(result)
        self.assertIn("body", text)
        self.assertIn("https://example.com/doc", text)
        self.assertIn("image/png", text)

    def test_empty_result_is_readable(self) -> None:
        self.assertIn("未返回内容", format_tool_result(SimpleNamespace(content=[])))

    def test_error_result_raises(self) -> None:
        connection = FakeConnection(
            "demo",
            result=SimpleNamespace(
                content=[SimpleNamespace(type="text", text="参数错误")],
                isError=True,
            ),
        )
        tool = MCPTool(
            exposed_name="lookup",
            remote_name="lookup",
            server_name="demo",
            description="",
            parameters={},
            connection=connection,
        )
        with self.assertRaises(MCPToolError) as ctx:
            tool.execute(q="x")
        self.assertIn("参数错误", str(ctx.exception))
        self.assertEqual(connection.calls, [("lookup", {"q": "x"})])

    def test_connection_error_is_propagated_as_tool_error(self) -> None:
        from core.exceptions import MCPConnectionError

        connection = FakeConnection("demo", error=MCPConnectionError("连接中断"))
        tool = MCPTool(
            exposed_name="lookup",
            remote_name="lookup",
            server_name="demo",
            description="",
            parameters={},
            connection=connection,
        )
        with self.assertRaises(MCPConnectionError):
            tool.execute()

    def test_result_is_error_compat(self) -> None:
        self.assertTrue(result_is_error(SimpleNamespace(isError=True)))
        self.assertTrue(result_is_error(SimpleNamespace(is_error=True)))
        self.assertFalse(result_is_error(SimpleNamespace()))


class MCPManagerFailureTest(unittest.TestCase):
    def test_bad_config_does_not_raise_and_keeps_registry_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".mcp.json"
            path.write_text(
                json.dumps(
                    {"mcpServers": {"bad": {"type": "stdio", "command": "python"}}}
                ),
                encoding="utf-8",
            )
            registry = ToolRegistry(
                [
                    FunctionTool(
                        lambda: "ok",
                        name="local",
                        description="本地工具",
                        parameters={"type": "object", "properties": {}},
                    )
                ]
            )
            manager = MCPManager(project_root=tmp)
            manager.register(registry)

        self.assertEqual(manager.connections, {})
        self.assertTrue(manager.errors)
        self.assertEqual(registry.get("local").execute(), "ok")
        buffer = io.StringIO()
        manager.report_errors(buffer)
        self.assertIn("[MCP]", buffer.getvalue())

    def test_malformed_config_is_reported_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".mcp.json").write_text("{", encoding="utf-8")
            manager = MCPManager(project_root=tmp)
            manager.connect()
        self.assertTrue(any("格式错误" in message for message in manager.errors))

    def test_missing_config_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = MCPManager(project_root=tmp)
            manager.connect()
        self.assertEqual(manager.errors, [])
        self.assertEqual(manager.connections, {})


class MCPDiagnosticTest(unittest.TestCase):
    def test_tool_error_includes_sdk_error_detail(self) -> None:
        from core.mcp.transport import describe_exception

        error = RuntimeError("Error executing tool list_pets")
        error.error = {"code": -32603, "message": "backend unavailable"}
        detail = describe_exception(error)
        self.assertIn("Error executing tool list_pets", detail)
        self.assertIn("backend unavailable", detail)


if __name__ == "__main__":
    unittest.main()
