"""OpenAI 兼容接口实现。"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, AsyncIterator, Sequence

from core.config.settings import LLMSettings
from core.exceptions import LLMError
from core.llm.base import LLMClient, LLMResponse, StreamChunk, ToolCallDelta
from core.models.messages import Message


def _build_http_client(timeout: float) -> Any:
    """构建 httpx.AsyncClient，绕过系统代理直连 loopback 地址。

    httpx 默认 trust_env=True 会读取 HTTP_PROXY/HTTPS_PROXY 环境变量，
    且不会自动绕过 127.0.0.1/localhost，导致本地模型网关请求被错误转发
    到系统代理（如 Clash），引发 Connection error。

    通过 mounts 显式将 loopback 流量设为无代理（None），其余地址
    仍走默认的信任环境行为。
    """
    import httpx

    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0),
        mounts={
            "all://127.0.0.1": None,
            "all://localhost": None,
        },
    )


def _translate_exception(exc: Exception, context: str = "请求") -> LLMError:
    """将 openai/httpx 异常翻译为可操作的中文错误消息。

    openai SDK 的 APIConnectionError 固定显示 "Connection error."，
    真实原因藏在 __cause__（httpx.ConnectError / httpx.TimeoutException 等）中。
    此函数提取底层原因并给出可操作的中文说明。
    """
    exc_type = type(exc).__name__

    # openai SDK 异常 → httpx cause
    cause = getattr(exc, "__cause__", None) or exc
    cause_type = type(cause).__name__
    cause_msg = str(cause) if cause is not exc else ""

    # ---- 连接类错误（openai.APIConnectionError）----
    if exc_type == "APIConnectionError":
        if cause_type in ("ConnectError", "ConnectTimeout", "ConnectionRefusedError"):
            # 尝试提取目标地址
            target = ""
            try:
                if hasattr(cause, "request") and cause.request:
                    url = getattr(cause.request, "url", "")
                    target = f"（目标地址：{url}）" if url else ""
            except Exception:
                pass
            if "refused" in cause_msg.lower() or cause_type == "ConnectionRefusedError":
                return LLMError(
                    f"连接被拒绝{target}。目标端口可能没有服务在监听，"
                    f"请检查 base_url 地址和端口是否正确，或确认模型服务已启动。"
                )
            if "timeout" in cause_msg.lower() or cause_type in ("ConnectTimeout", "TimeoutException"):
                return LLMError(
                    f"连接超时{target}。目标服务在 {getattr(exc, 'timeout', '')} 内未响应，"
                    f"请确认网络可达或增大 timeout 配置。"
                )
            return LLMError(
                f"无法连接到模型服务{target}。底层错误：{cause_msg or cause_type}。"
                f"请检查 base_url 是否正确、服务是否已启动、或是否存在代理拦截。"
            )
        if cause_type in ("ReadTimeout", "PoolTimeout"):
            return LLMError(
                f"读取响应超时。模型服务连接成功但未在规定时间内返回数据，"
                f"请增大 timeout 配置或检查服务负载。"
            )
        # 兜底
        return LLMError(
            f"连接模型服务失败：{cause_msg or exc_type}。"
            f"可能原因：端口未监听、代理拦截、DNS 解析失败或网络不可达。"
        )

    # ---- 超时类（openai.APITimeoutError）----
    if exc_type == "APITimeoutError":
        return LLMError(
            f"请求超时。模型服务未在规定时间内响应，"
            f"请增大 timeout 配置或检查服务状态。"
        )

    # ---- 认证类 ----
    if exc_type == "AuthenticationError":
        return LLMError(
            f"API Key 认证失败（401）。请检查 api_key 是否正确、"
            f"是否已过期或属于当前 base_url 对应的服务。"
        )

    # ---- 资源不存在 ----
    if exc_type == "NotFoundError":
        return LLMError(
            f"请求的资源不存在（404）。请检查 base_url 路径和 model 名称是否正确。"
        )

    # ---- 限流 ----
    if exc_type == "RateLimitError":
        return LLMError(
            f"请求被限流（429）。请降低请求频率或联系服务提供商提升配额。"
        )

    # ---- 服务端错误 ----
    if exc_type == "InternalServerError":
        return LLMError(
            f"模型服务内部错误（5xx）。请稍后重试或检查服务端日志。"
        )

    # ---- 未知异常：保留原始信息 ----
    err = LLMError(f"{context}失败：{exc}")
    err.__cause__ = exc
    return err


def _usage_dict(usage: Any) -> dict[str, Any] | None:
    """把 SDK 的 usage 对象转换成普通字典。"""
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        data = usage.model_dump()
    elif isinstance(usage, dict):
        data = dict(usage)
    else:
        try:
            data = dict(usage)
        except (TypeError, ValueError):
            return None
    result: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            result[key] = int(value)
    return result or None


class OpenAICompatibleClient(LLMClient):
    """基于 openai SDK 的兼容客户端（DeepSeek / OpenAI / 各类网关）。"""

    def __init__(self, settings: LLMSettings) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError("未安装 openai SDK，请执行 pip install openai") from exc

        self.settings = settings
        self.model = settings.model
        # 传入自定义 httpx client，绕过系统代理直连 loopback 地址
        self._http_client = _build_http_client(settings.timeout)
        self._client = AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout,
            http_client=self._http_client,
        )

    def _request_kwargs(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": list(messages),
            "temperature": self.settings.temperature,
        }
        if self.settings.max_tokens:
            kwargs["max_tokens"] = self.settings.max_tokens
        if tools:
            kwargs["tools"] = list(tools)
            kwargs["tool_choice"] = "auto"
        return kwargs

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        try:
            response = await self._client.chat.completions.create(
                **self._request_kwargs(messages, tools)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise _translate_exception(exc, "非流式请求") from exc

        if not response.choices:
            raise LLMError("模型返回了空结果。")

        raw_message = response.choices[0].message
        dump = raw_message.model_dump() if hasattr(raw_message, "model_dump") else dict(raw_message)
        return LLMResponse(
            message=Message.from_api(dump),
            raw=response,
            usage=_usage_dict(getattr(response, "usage", None)),
        )

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        kwargs = self._request_kwargs(messages, tools)
        kwargs["stream"] = True
        # 请求流式接口返回 usage，便于上层精确统计上下文长度。
        kwargs["stream_options"] = {"include_usage": True}
        try:
            stream = await self._client.chat.completions.create(**kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 少数兼容网关不支持 stream_options，去掉该参数后重试一次。
            message = str(exc).lower()
            retryable = (
                "stream_options" in message
                or "include_usage" in message
                or "unknown parameter" in message
                or "unrecognized" in message
            )
            if not retryable:
                raise _translate_exception(exc, "流式请求") from exc
            kwargs.pop("stream_options", None)
            try:
                stream = await self._client.chat.completions.create(**kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as retry_exc:
                raise _translate_exception(retry_exc, "流式请求") from retry_exc

        completed = False
        try:
            async for chunk in stream:
                usage = _usage_dict(getattr(chunk, "usage", None))
                if not chunk.choices:
                    if usage:
                        yield StreamChunk(usage=usage)
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                tool_deltas: list[ToolCallDelta] = []
                for item in getattr(delta, "tool_calls", None) or []:
                    function = getattr(item, "function", None)
                    arguments = getattr(function, "arguments", "") if function else ""
                    tool_deltas.append(
                        ToolCallDelta(
                            index=getattr(item, "index", 0) or 0,
                            id=getattr(item, "id", None),
                            name=getattr(function, "name", None) if function else None,
                            arguments=arguments or "",
                        )
                    )
                yield StreamChunk(
                    delta=getattr(delta, "content", "") or "",
                    tool_calls=tool_deltas,
                    finish_reason=getattr(choice, "finish_reason", None),
                    usage=usage,
                )
            completed = True
            return
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except LLMError:
            raise
        except Exception as exc:
            raise _translate_exception(exc, "流式响应中断") from exc
        finally:
            if not completed:
                await self._close_stream(stream)

    @staticmethod
    async def _close_stream(stream: Any) -> None:
        """尽力关闭流对象，兼容同步/异步 close 接口。"""
        for method_name in ("aclose", "close"):
            method = getattr(stream, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                if inspect.isawaitable(result):
                    await result
            except BaseException:
                pass
            return

    async def aclose(self) -> None:
        """释放底层 HTTP 连接，供程序退出时调用。"""
        await self._client.close()
        # 关闭自定义 httpx client（如果 openai SDK 内部未接管生命周期）
        if hasattr(self._http_client, "aclose"):
            try:
                await self._http_client.aclose()
            except BaseException:
                pass
