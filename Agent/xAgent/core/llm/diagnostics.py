"""模型服务连通性诊断。

提供独立于 TUI 的诊断能力，用于快速定位"Connection error"类问题的根因：
  1. 配置检查 —— base_url/model/api_key 是否存在且格式合理
  2. 端口探测 —— 目标端口是否有服务在监听
  3. HTTP 探活 —— 直连（绕过代理）能否到达 /v1/models 或 /v1/chat/completions
  4. 代理检测 —— 系统是否设置了 HTTP_PROXY/HTTPS_PROXY，是否会劫持 loopback
  5. API Key 验证 —— 发送一次最小请求，检查认证是否通过
"""

from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from core.config.settings import LLMSettings


@dataclass(slots=True)
class CheckResult:
    """单项检查结果。"""

    name: str
    ok: bool
    detail: str = ""
    hint: str = ""


@dataclass(slots=True)
class DiagnosticsReport:
    """完整诊断报告。"""

    base_url: str = ""
    model: str = ""
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def summary(self) -> str:
        """生成可读的中文报告。"""
        lines: list[str] = []
        lines.append(f"接口地址：{self.base_url or '(未配置)'}")
        lines.append(f"模型名称：{self.model or '(未配置)'}")
        lines.append("")
        for c in self.checks:
            icon = "[OK]" if c.ok else "[FAIL]"
            lines.append(f"{icon} {c.name}")
            if c.detail:
                lines.append(f"      {c.detail}")
            if c.hint:
                lines.append(f"      → {c.hint}")
        lines.append("")
        if self.all_ok:
            lines.append("全部检查通过，模型服务应该可以正常连接。")
        else:
            failed = [c.name for c in self.checks if not c.ok]
            lines.append(f"未通过检查：{', '.join(failed)}")
        return "\n".join(lines)


def _parse_host_port(base_url: str) -> tuple[str, int] | None:
    """从 base_url 中提取 host 和 port，解析失败返回 None。"""
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname
        if not host:
            return None
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        return host, port
    except Exception:
        return None


def _check_config(settings: LLMSettings) -> CheckResult:
    """检查配置字段是否齐全。"""
    missing: list[str] = []
    if not settings.base_url:
        missing.append("base_url")
    if not settings.model:
        missing.append("model")
    if not settings.api_key:
        missing.append("api_key")

    if missing:
        return CheckResult(
            name="配置完整性",
            ok=False,
            detail=f"缺少必要配置项：{', '.join(missing)}",
            hint="请在 config.ini 的 [llm] 段补全上述字段，或设置对应环境变量。",
        )
    return CheckResult(
        name="配置完整性",
        ok=True,
        detail=f"base_url={settings.base_url}, model={settings.model}",
    )


def _check_port(host: str, port: int, timeout: float = 3.0) -> CheckResult:
    """检查目标 host:port 是否有服务在监听。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            return CheckResult(
                name="端口监听",
                ok=True,
                detail=f"{host}:{port} 有服务在监听。",
            )
        return CheckResult(
            name="端口监听",
            ok=False,
            detail=f"{host}:{port} 连接被拒绝（errno={result}），该端口没有服务在监听。",
            hint="请确认模型服务/网关已启动，并监听在配置的端口上。",
        )
    except socket.gaierror as exc:
        return CheckResult(
            name="端口监听",
            ok=False,
            detail=f"DNS 解析失败：{host} 无法解析（{exc}）。",
            hint="请检查 base_url 中的主机名拼写是否正确。",
        )
    except Exception as exc:
        return CheckResult(
            name="端口监听",
            ok=False,
            detail=f"端口探测异常：{type(exc).__name__}: {exc}",
        )


def _check_proxy(base_url: str) -> CheckResult:
    """检测系统代理是否会劫持 loopback 请求。"""
    proxy_vars = {
        "HTTP_PROXY": os.environ.get("HTTP_PROXY", ""),
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY", ""),
        "http_proxy": os.environ.get("http_proxy", ""),
        "https_proxy": os.environ.get("https_proxy", ""),
    }
    active_proxies = {k: v for k, v in proxy_vars.items() if v}

    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    is_loopback = host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    if not active_proxies:
        return CheckResult(
            name="代理检测",
            ok=True,
            detail="未检测到系统代理环境变量。",
        )

    if is_loopback:
        return CheckResult(
            name="代理检测",
            ok=True,
            detail=(
                f"检测到代理：{active_proxies}。"
                f"但目标地址 {host} 是 loopback，已通过 httpx mounts 绕过代理直连。"
            ),
        )

    return CheckResult(
        name="代理检测",
        ok=True,
        detail=f"检测到代理：{active_proxies}。目标地址 {host} 非 loopback，请求将经由代理转发。",
        hint="如果代理不可用，请清除 HTTP_PROXY/HTTPS_PROXY 环境变量。",
    )


async def _check_http_reachable(
    base_url: str, api_key: str, timeout: float = 10.0
) -> CheckResult:
    """发送一次最小 HTTP 请求验证连通性和认证。"""
    try:
        import httpx
    except ImportError:
        return CheckResult(
            name="HTTP 探活",
            ok=False,
            detail="未安装 httpx，无法执行 HTTP 探活。",
        )

    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    is_loopback = host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    # 构建 client：loopback 地址绕过代理
    mounts: dict[str, Any] = {}
    if is_loopback:
        mounts = {
            "all://127.0.0.1": None,
            "all://localhost": None,
        }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            mounts=mounts,
        ) as client:
            # 尝试 GET /v1/models（大多数 OpenAI 兼容服务支持）
            models_url = base_url.rstrip("/") + "/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = await client.get(models_url, headers=headers)

            if resp.status_code == 200:
                return CheckResult(
                    name="HTTP 探活",
                    ok=True,
                    detail=f"GET /v1/models 返回 200，服务可达且认证通过。",
                )
            if resp.status_code == 401:
                return CheckResult(
                    name="HTTP 探活",
                    ok=False,
                    detail=f"GET /v1/models 返回 401 Unauthorized。",
                    hint="api_key 不正确或已过期，请检查配置。",
                )
            if resp.status_code == 404:
                # /models 不支持但服务本身可达
                return CheckResult(
                    name="HTTP 探活",
                    ok=True,
                    detail=f"GET /v1/models 返回 404（服务可达，但可能不支持 /models 端点）。",
                )
            if resp.status_code == 429:
                return CheckResult(
                    name="HTTP 探活",
                    ok=False,
                    detail=f"GET /v1/models 返回 429 Too Many Requests。",
                    hint="请求被限流，请降低频率或提升配额。",
                )
            return CheckResult(
                name="HTTP 探活",
                ok=False,
                detail=f"GET /v1/models 返回 HTTP {resp.status_code}。",
            )
    except httpx.ConnectError as exc:
        exc_msg = str(exc).lower()
        if "refused" in exc_msg:
            return CheckResult(
                name="HTTP 探活",
                ok=False,
                detail=f"连接被拒绝：{base_url}。目标端口没有服务在监听。",
                hint="请确认模型服务已启动并监听在正确端口。",
            )
        if "timeout" in exc_msg or "timed out" in exc_msg:
            return CheckResult(
                name="HTTP 探活",
                ok=False,
                detail=f"连接超时：{base_url}。目标地址在 {timeout}s 内不可达。",
                hint="请检查网络连通性或增大 timeout 配置。",
            )
        return CheckResult(
            name="HTTP 探活",
            ok=False,
            detail=f"连接失败：{exc}",
            hint="可能原因：端口未监听、代理拦截、DNS 解析失败或网络不可达。",
        )
    except httpx.ConnectTimeout:
        return CheckResult(
            name="HTTP 探活",
            ok=False,
            detail=f"连接超时：{base_url}。目标地址在 {timeout}s 内不可达。",
            hint="请检查网络连通性或增大 timeout 配置。",
        )
    except httpx.ProxyError as exc:
        return CheckResult(
            name="HTTP 探活",
            ok=False,
            detail=f"代理错误：{exc}。",
            hint="系统代理不可用，请清除 HTTP_PROXY/HTTPS_PROXY 或修复代理服务。",
        )
    except Exception as exc:
        return CheckResult(
            name="HTTP 探活",
            ok=False,
            detail=f"HTTP 请求异常：{type(exc).__name__}: {exc}",
        )


async def run_diagnostics(settings: LLMSettings) -> DiagnosticsReport:
    """执行完整诊断，返回报告。"""
    report = DiagnosticsReport(
        base_url=settings.base_url,
        model=settings.model,
    )

    # 1. 配置检查
    config_check = _check_config(settings)
    report.checks.append(config_check)
    if not config_check.ok:
        # 配置不全，后续检查无意义
        return report

    # 2. 端口探测
    hp = _parse_host_port(settings.base_url)
    if hp:
        host, port = hp
        port_check = _check_port(host, port)
    else:
        port_check = CheckResult(
            name="端口监听",
            ok=False,
            detail=f"无法从 base_url 解析出 host:port：{settings.base_url}",
        )
    report.checks.append(port_check)

    # 3. 代理检测
    proxy_check = _check_proxy(settings.base_url)
    report.checks.append(proxy_check)

    # 4. HTTP 探活
    http_check = await _check_http_reachable(
        settings.base_url, settings.api_key, settings.timeout
    )
    report.checks.append(http_check)

    return report
