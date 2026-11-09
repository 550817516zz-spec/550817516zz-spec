"""内置工具：基于百度千帆 AI 搜索的联网检索。"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from core.tools.base import FunctionTool

SEARCH_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"
DEFAULT_TIMEOUT = 20.0
MAX_QUERY_LENGTH = 72
MAX_RESULTS = 50
MAX_CONTENT_PER_ITEM = 300
MAX_TOTAL_LENGTH = 6000


def _post_json(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
    """向搜索接口发送 JSON 请求并返回解析后的响应。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "xAgent/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """尽量从错误响应体中提取 code / message。"""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except Exception:
        return exc.reason or "未知错误"
    if isinstance(data, dict):
        message = data.get("message") or data.get("error_msg") or data.get("error")
        code = data.get("code") or data.get("error_code")
        if code and message:
            return f"{code}: {message}"
        if message:
            return str(message)
    return exc.reason or "未知错误"


def _format_references(
    query: str,
    references: list[dict[str, Any]],
    *,
    max_content_per_item: int = MAX_CONTENT_PER_ITEM,
    max_total_length: int = MAX_TOTAL_LENGTH,
) -> str:
    """把 references 整理成模型易读的纯文本。"""
    lines: list[str] = [f"关于「{query}」的搜索结果："]
    total = len(lines[0])
    for index, reference in enumerate(references, start=1):
        title = str(reference.get("title") or reference.get("web_anchor") or "").strip() or "（无标题）"
        url = str(reference.get("url") or "").strip()
        content = str(reference.get("content") or reference.get("snippet") or "").strip()
        date = str(reference.get("date") or "").strip()[:19]

        heading = f"{index}. {title}"
        if date:
            heading += f"（{date}）"
        block = [heading]
        if url:
            block.append(f"   {url}")
        if content:
            if len(content) > max_content_per_item:
                content = content[:max_content_per_item] + "…"
            block.append(f"   {content}")

        text = "\n".join(block)
        if total + len(text) > max_total_length:
            lines.append("（结果过多，已截断）")
            break
        lines.append(text)
        total += len(text)

    return "\n".join(lines)


def build_search_tools(
    api_key: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    endpoint: str = SEARCH_ENDPOINT,
    max_query_length: int = MAX_QUERY_LENGTH,
    max_results: int = MAX_RESULTS,
    max_content_per_item: int = MAX_CONTENT_PER_ITEM,
    max_total_length: int = MAX_TOTAL_LENGTH,
) -> list[FunctionTool]:
    """构建联网搜索工具；api_key 为空时工具会返回配置提示。"""

    def web_search(query: str, top_k: int = 10) -> str:
        """使用百度千帆 AI 搜索在互联网上检索实时信息。

        Args:
            query: 搜索关键词或问题，建议不超过 72 个字符
            top_k: 返回的结果数量，范围 1-50，默认 10
        """
        text = (query or "").strip()
        if not text:
            return "请提供搜索关键词。"
        if len(text) > max_query_length:
            text = text[:max_query_length]
        if not api_key:
            return "未配置搜索服务：请在 config.ini 的 [search] 段填写 baidu_qianfan_api_key。"

        try:
            count = int(top_k)
        except (TypeError, ValueError):
            count = 10
        count = max(1, min(max_results, count))

        payload = {
            "messages": [{"role": "user", "content": text}],
            "edition": "standard",
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": count}],
        }

        try:
            data = _post_json(endpoint, payload, api_key, timeout)
        except urllib.error.HTTPError as exc:
            return f"搜索请求失败（HTTP {exc.code}）：{_error_detail(exc)}"
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            return f"搜索请求失败：网络错误（{reason}）"
        except json.JSONDecodeError:
            return "搜索请求失败：接口返回了无法解析的内容。"
        except Exception as exc:
            return f"搜索请求失败：{type(exc).__name__}: {exc}"

        references = data.get("references") if isinstance(data, dict) else None
        if not isinstance(references, list) or not references:
            return f"未找到与「{text}」相关的结果。"
        return _format_references(
            text,
            [item for item in references if isinstance(item, dict)],
            max_content_per_item=max_content_per_item,
            max_total_length=max_total_length,
        )

    def searchWeb(query: str, top_k: int = 10) -> str:
        """通过百度千帆智能搜索生成API获取最新信息。
        
        Args:
            query: 搜索关键词或问题
            top_k: 返回的结果数量，范围 1-50，默认 10
        """
        return web_search(query=query, top_k=top_k)

    return [
        FunctionTool(
            web_search,
            name="web_search",
            description="使用百度千帆 AI 搜索联网检索实时信息，返回标题、链接与摘要。",
        ),
        FunctionTool(
            searchWeb,
            name="searchWeb",
            description="使用百度千帆智能搜索生成API搜索互联网，获取最新信息并返回搜索摘要、参考来源的标题及URL。",
        ),
    ]


__all__ = ["build_search_tools", "SEARCH_ENDPOINT"]
