"""
Pet Hospital MCP Server (MVP)
只实现一个工具: list_pets -> GET /api/v1/pets (过滤 + 排序 + 分页)

依赖: mcp>=2.0.0, requests
运行: python server.py
"""

import os

import requests
from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get("PETHOSPITAL_BASE_URL", "http://127.0.0.1:8080").rstrip("/")

# 只保留列表要看的字段, 丢掉 records/charges 等大字段, 省 token
KEEP = (
    "id", "name", "species", "breed", "gender", "ageMonths",
    "ownerName", "ownerPhone", "doctor", "disease", "status",
    "totalCost", "visitCount",
)

mcp = MCPServer("pet-hospital")


@mcp.tool()
def list_pets(
    name: str = "",
    species: str = "",
    status: str = "",
    doctor: str = "",
    disease: str = "",
    ownerName: str = "",
    sortBy: str = "id",
    order: str = "asc",
    page: int = 1,
    pageSize: int = 20,
) -> dict:
    """查询宠物医院档案列表（支持过滤 + 排序 + 分页）。

    参数:
        name: 按宠物名字模糊过滤, 留空不过滤
        species: 按种类过滤, 如 犬/猫/兔/鸟, 留空不过滤
        status: 按就诊状态过滤, 如 待就诊/就诊中/住院中/已康复/慢性病随访
        doctor: 按接诊医生过滤
        disease: 按疾病过滤
        ownerName: 按主人姓名模糊过滤
        sortBy: 排序字段, 默认 id, 也可用 name/totalCost/visitCount
        order: 排序方向, asc 或 desc
        page: 页码, 从 1 开始
        pageSize: 每页条数, 建议不超过 50 以免撑爆上下文
    """
    params = {
        "name": name, "species": species, "status": status, "doctor": doctor,
        "disease": disease, "ownerName": ownerName,
        "sortBy": sortBy, "order": order, "page": page, "pageSize": pageSize,
    }
    params = {k: v for k, v in params.items() if v not in ("", None)}

    resp = requests.get(f"{BASE_URL}/api/v1/pets", params=params, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 200:
        return {"error": body.get("message", "unknown error")}

    d = body["data"]
    return {
        "total": d["total"],
        "page": d["page"],
        "pageSize": d["pageSize"],
        "totalPages": d["totalPages"],
        "items": [{k: p.get(k) for k in KEEP} for p in d["items"]],
    }


if __name__ == "__main__":
    # stateless_http + json_response: 每次请求独立完成, 不需要 initialize 握手,
    # 不保持 SSE 长连接, 同时兼容 2026-07-28 前后两版协议
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8766,
        stateless_http=True,
        json_response=True,
    )
