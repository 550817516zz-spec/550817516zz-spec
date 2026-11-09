"""MCP Streamable HTTP 连接。

MCP Python SDK 的客户端 API 是异步的，而 xAgent 现有的工具执行接口是同步的。
这里用一个常驻后台线程持有独立事件循环，并在同一个任务中完成连接的建立、
``list_tools``、``call_tool`` 与关闭，避免 AsyncExitStack / anyio cancel scope
跨任务退出导致的问题。

同时兼容 MCP Python SDK 1.x 与 2.x：

* 1.x：``streamablehttp_client``，返回 ``(read, write, get_session_id)``；
* 2.x：``streamable_http_client``，返回 ``(read, write)``，自定义 Header 需传入
  ``httpx`` 客户端。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from core.exceptions import MCPConnectionError, MCPError
from core.mcp.config import MCPServerConfig

try:  # pragma: no cover - 导入失败时在真正使用 MCP 时给出明确提示
    from mcp import ClientSession
    from mcp.client import streamable_http as _streamable_http
except Exception as exc:  # noqa: BLE001 - 记录原始导入错误
    ClientSession = None  # type: ignore[assignment]
    _streamable_http = None  # type: ignore[assignment]
    _MCP_IMPORT_ERROR: Exception | None = exc
else:
    _MCP_IMPORT_ERROR = None

_V2_TRANSPORT = (
    getattr(_streamable_http, "streamable_http_client", None)
    if _streamable_http is not None
    else None
)
_V1_TRANSPORT = (
    getattr(_streamable_http, "streamablehttp_client", None)
    if _streamable_http is not None
    else None
)
_CREATE_HTTP_CLIENT = (
    getattr(_streamable_http, "create_mcp_http_client", None)
    if _streamable_http is not None
    else None
)


def describe_exception(exc: BaseException) -> str:
    """把 anyio / asyncio 的异常组展开成一行可读信息。"""
    # Python 3.11+ 的 ExceptionGroup，以及兼容旧版本的鸭子类型判断。
    inner = getattr(exc, "exceptions", None)
    if isinstance(inner, (list, tuple)) and inner:
        parts: list[str] = []
        for item in inner:
            text = describe_exception(item)
            if text and text not in parts:
                parts.append(text)
        if parts:
            return "；".join(parts)
    message = str(exc).strip()
    # SDK 的 ToolError 常把 JSON-RPC 错误对象放在 error 属性中，
    # 但自身字符串只显示笼统的 "Error executing tool <name>"。
    detail = getattr(exc, "error", None)
    if detail is not None:
        detail_text = str(detail).strip()
        if detail_text and detail_text not in message:
            message = f"{message}: {detail_text}" if message else detail_text
    name = type(exc).__name__
    if message:
        return f"{name}: {message}"
    return name


def _first_exception(exc: BaseException) -> BaseException:
    """取异常组中最内层、最有信息量的异常。"""
    current = exc
    for _ in range(8):
        inner = getattr(current, "exceptions", None)
        if not isinstance(inner, (list, tuple)) or not inner:
            break
        current = inner[0]
    return current


@asynccontextmanager
async def _open_streams(
    config: MCPServerConfig,
) -> AsyncIterator[tuple[Any, Any]]:
    """打开 Streamable HTTP 传输并返回读写流。"""
    if _V2_TRANSPORT is not None:
        http_client = None
        try:
            if config.headers:
                if _CREATE_HTTP_CLIENT is None:
                    raise MCPConnectionError(
                        f"MCP Server「{config.name}」配置了 headers，但当前 MCP SDK "
                        "未提供 create_mcp_http_client，无法附加请求头。"
                    )
                http_client = _CREATE_HTTP_CLIENT(headers=dict(config.headers))
            async with _V2_TRANSPORT(
                config.url,
                http_client=http_client,
                terminate_on_close=False,
            ) as streams:
                read_stream, write_stream = streams[0], streams[1]
                yield read_stream, write_stream
        finally:
            if http_client is not None:
                try:
                    await http_client.aclose()
                except Exception:
                    pass
        return

    if _V1_TRANSPORT is not None:
        kwargs: dict[str, Any] = {}
        try:
            parameters = inspect.signature(_V1_TRANSPORT).parameters
        except (TypeError, ValueError):  # pragma: no cover - 极少见
            parameters = {}
        if "headers" in parameters and config.headers:
            kwargs["headers"] = dict(config.headers)
        if "timeout" in parameters:
            kwargs["timeout"] = config.timeout
        if "sse_read_timeout" in parameters:
            kwargs["sse_read_timeout"] = max(config.timeout, 300.0)
        if "terminate_on_close" in parameters:
            kwargs["terminate_on_close"] = False
        async with _V1_TRANSPORT(config.url, **kwargs) as streams:
            read_stream, write_stream = streams[0], streams[1]
            yield read_stream, write_stream
        return

    raise MCPConnectionError(
        "当前 MCP SDK 不包含 Streamable HTTP 客户端。"
        "请安装 mcp>=1.8（推荐使用最新版本）。"
    )


class MCPConnection:
    """一个 MCP Server 的常驻连接。"""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.name = config.name
        self._tools: list[Any] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._queue: asyncio.Queue[Any] | None = None
        self._owner_task: asyncio.Task[Any] | None = None
        self._ready: concurrent.futures.Future[list[Any]] = concurrent.futures.Future()
        self._closed = False
        self._closing = False
        self._started = False
        self._connection_error: BaseException | None = None
        self._state_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @property
    def tools(self) -> list[Any]:
        return list(self._tools)

    @property
    def connected(self) -> bool:
        return self._started and not self._closed and not self._closing

    def start(self) -> None:
        """启动后台线程并等待初始化与工具发现完成。"""
        if _MCP_IMPORT_ERROR is not None:
            raise MCPConnectionError(
                "未安装可用的 MCP Python SDK，请执行 `pip install \"mcp>=1.8\"`。"
                f"原始错误：{describe_exception(_MCP_IMPORT_ERROR)}"
            ) from _MCP_IMPORT_ERROR

        with self._state_lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._thread_main,
                name=f"mcp-{self.name}",
                daemon=True,
            )
            self._thread.start()

        try:
            self._tools = self._ready.result(timeout=self.config.timeout + 5.0)
            self._started = True
        except concurrent.futures.TimeoutError as exc:
            self.close()
            raise MCPConnectionError(
                f"MCP Server「{self.name}」连接超时（{self.config.timeout:g} 秒）：{self.config.url}"
            ) from exc
        except BaseException as exc:
            self.close()
            root = _first_exception(exc)
            raise MCPConnectionError(
                f"MCP Server「{self.name}」连接失败：{describe_exception(root)}（{self.config.url}）"
            ) from exc

    def close(self, timeout: float = 5.0) -> None:
        """关闭连接；可重复调用。"""
        with self._state_lock:
            if self._closed and (self._thread is None or not self._thread.is_alive()):
                return
            self._closing = True
            loop = self._loop
            queue = self._queue
            thread = self._thread
            owner_task = self._owner_task

        if loop is not None and queue is not None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except RuntimeError:
                pass

        if thread is not None:
            thread.join(timeout)
            if thread.is_alive() and loop is not None and owner_task is not None:
                # 连接/调用可能卡在网络上；取消常驻任务，强制退出 await。
                try:
                    loop.call_soon_threadsafe(owner_task.cancel)
                except RuntimeError:
                    pass
                thread.join(timeout)

        with self._state_lock:
            self._closed = True
            self._closing = True
            self._started = False
            self._thread = None

    # ------------------------------------------------------------------
    # 后台事件循环
    # ------------------------------------------------------------------
    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._owner())
        except BaseException as exc:  # noqa: BLE001 - 兜底通知等待方
            if not self._ready.done():
                self._ready.set_exception(exc)
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    async def _owner(self) -> None:
        """在同一个任务中持有连接并串行处理所有请求。"""
        self._owner_task = asyncio.current_task()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._queue = queue

        try:
            async with _open_streams(self.config) as (read_stream, write_stream):
                assert ClientSession is not None
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self._tools = await self._list_tools(session)
                    if not self._ready.done():
                        self._ready.set_result(self._tools)
                    await self._serve(session, queue)
        except asyncio.CancelledError:
            self._connection_error = MCPConnectionError(
                f"MCP Server「{self.name}」连接已关闭。"
            )
        except BaseException as exc:  # noqa: BLE001 - 传递给调用方
            self._connection_error = exc
            if not self._ready.done():
                self._ready.set_exception(exc)
        finally:
            error = self._connection_error or MCPConnectionError(
                f"MCP Server「{self.name}」连接已断开。"
            )
            with self._state_lock:
                self._closed = True
                self._started = False
                self._fail_pending(queue, error)

    async def _serve(
        self,
        session: Any,
        queue: asyncio.Queue[Any],
    ) -> None:
        while True:
            item = await queue.get()
            if item is None:
                return
            future, factory = item
            if future.cancelled():
                continue
            try:
                result = await factory(session)
            except BaseException as exc:  # noqa: BLE001 - 原样交给调用线程
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(result)

    def _fail_pending(self, queue: asyncio.Queue[Any], error: BaseException) -> None:
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                continue
            future, _ = item
            if not future.done():
                future.set_exception(error)

    async def _list_tools(self, session: Any) -> list[Any]:
        """调用 ``list_tools``；兼容分页与 1.x / 2.x 的参数名。"""
        collected: list[Any] = []
        cursor: Any = None
        for _ in range(100):  # 防御异常 Server 无限分页
            if cursor:
                try:
                    result = await session.list_tools(cursor=cursor)
                except TypeError:
                    result = await session.list_tools(params={"cursor": cursor})
            else:
                result = await session.list_tools()

            tools = getattr(result, "tools", None)
            if tools is None and isinstance(result, dict):
                tools = result.get("tools")
            if tools:
                collected.extend(tools)

            cursor = getattr(result, "nextCursor", None)
            if cursor is None:
                cursor = getattr(result, "next_cursor", None)
            if not cursor:
                break
        return collected

    # ------------------------------------------------------------------
    # 同步调用接口
    # ------------------------------------------------------------------
    def call_tool(
        self,
        remote_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """转发 ``call_tool`` 并同步等待结果。"""
        loop = self._loop
        queue = self._queue
        if loop is None or queue is None or not loop.is_running():
            raise MCPConnectionError(
                f"MCP Server「{self.name}」尚未连接，无法调用工具「{remote_name}」。"
            )

        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        async def invoke(session: Any) -> Any:
            return await session.call_tool(remote_name, arguments or {})

        with self._state_lock:
            if self._closed or self._closing:
                raise MCPConnectionError(
                    f"MCP Server「{self.name}」连接已关闭，无法调用工具「{remote_name}」。"
                )
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (future, invoke))
            except RuntimeError as exc:
                raise MCPConnectionError(
                    f"MCP Server「{self.name}」事件循环已停止，无法调用工具「{remote_name}」。"
                ) from exc

        wait_timeout = timeout if timeout is not None else self.config.timeout
        try:
            return future.result(timeout=wait_timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise MCPConnectionError(
                f"调用 MCP Server「{self.name}」的工具「{remote_name}」超时"
                f"（{wait_timeout:g} 秒）。"
            ) from exc
        except MCPError:
            raise
        except BaseException as exc:  # noqa: BLE001 - 统一转换为可读错误
            root = _first_exception(exc)
            raise MCPConnectionError(
                f"调用 MCP Server「{self.name}」的工具「{remote_name}」失败："
                f"{describe_exception(root)}"
            ) from exc


__all__ = [
    "MCPConnection",
    "describe_exception",
]
