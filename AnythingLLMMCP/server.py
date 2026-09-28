"""
AnythingLLM MCP Server (MVP)
只实现一个功能: 提取第一个工作区里的文件(文档)信息。

依赖: mcp>=2.0.0, requests
运行: python server.py
"""

import os

import requests
from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
API_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "")

mcp = MCPServer("anythingllm-files")

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _get(path: str) -> dict:
    resp = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def list_workspace_files() -> dict:
    """提取 AnythingLLM 中第一个工作区里的所有文件信息。

    返回: 第一个工作区的名字/slug, 以及其中每个文档的文件名、路径、
    字符数、分块数等元数据。不返回文档正文, 避免撑爆上下文。
    """
    if not API_KEY:
        return {"error": "未设置 ANYTHINGLLM_API_KEY 环境变量"}

    ws_res = _get("/api/v1/workspaces")
    workspaces = ws_res.get("workspaces") or []
    if not workspaces:
        return {"error": "AnythingLLM 中没有任何工作区"}

    ws = workspaces[0]
    detail = _get(f"/api/v1/workspace/{ws['slug']}")
    docs = (detail.get("workspace") or {}).get("documents") or []

    return {
        "workspace": {"name": ws.get("name"), "slug": ws["slug"]},
        "fileCount": len(docs),
        "documentCount": ws.get("documentCount"),
        "files": [
            {
                "title": d.get("title") or d.get("docpath"),
                "docpath": d.get("docpath"),
                "chunkCount": d.get("chunkCount"),
                "tokenCount": d.get("token_count_estimate"),
            }
            for d in docs
        ],
    }


if __name__ == "__main__":
    # stateless_http + json_response: 每次请求独立完成, 不需要 initialize 握手,
    # 不保持 SSE 长连接, 同时兼容 2026-07-28 前后两版协议
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8765,
        stateless_http=True,
        json_response=True,
    )
