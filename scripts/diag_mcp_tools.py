r"""直接调 MCP server 列出所有工具的诊断脚本。

绕过 worker / LangChain / LLM，用 mcp 库裸连 server 调 `list_tools`，
打印 server 端真实返回的完整工具列表（name / description / inputSchema）。
对比 worker 日志里 `MCP tools loaded count=N`，就能定位：
  - server 端 list_tools 就只返回 N 个（→ 在 server 端补 register）
  - server 端实际返回更多但 client 只拿了 N 个（→ client 这边有 bug）

用法：
    .venv\Scripts\python scripts\diag_mcp_tools.py [name] [url]

默认：name=ncmj-server, url=http://10.0.104.126:8000/mcp
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

# 允许从仓库根目录直接运行
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


async def main(name: str, url: str) -> int:
    print(f"==> 连 MCP server")
    print(f"    name: {name}")
    print(f"    url:  {url}")

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        print("错误：缺少 mcp 依赖，请先激活 .venv")
        return 2

    try:
        async with streamablehttp_client(url, headers=None) as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=10.0)
                print("    initialize: OK\n")

                result = await session.list_tools()
                tools = list(getattr(result, "tools", []) or [])
                print(f"==> server 端 list_tools 返回 {len(tools)} 个工具\n")
                if not tools:
                    print("    （空列表——server 端确实没注册任何工具）")
                    return 0

                for i, t in enumerate(tools, 1):
                    name_t = getattr(t, "name", "?")
                    desc = getattr(t, "description", "") or ""
                    schema = getattr(t, "inputSchema", None) or {}
                    props = list((schema.get("properties") or {}).keys())
                    required = list(schema.get("required") or [])
                    print(f"  [{i:02d}] {name_t}")
                    if desc:
                        # 截断长描述
                        one_line = " ".join(desc.split())
                        if len(one_line) > 100:
                            one_line = one_line[:100] + "..."
                        print(f"        desc: {one_line}")
                    print(f"        params: {props}")
                    if required:
                        print(f"        required: {required}")
                    print()
                return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\n!! 失败: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "ncmj-server"
    url = sys.argv[2] if len(sys.argv) > 2 else "http://10.0.104.126:8000/mcp"
    raise SystemExit(asyncio.run(main(name, url)))
