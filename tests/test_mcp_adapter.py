"""MCP adapter 桥接测试（不依赖真实 MCP server，使用 fake manager）。"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from langchain_core.tools import BaseTool

from app.worker.mcp.adapter import mcp_to_langchain_tools
from app.worker.mcp.client import MCPClientManager
from app.worker.mcp.registry import ToolRegistry
from config.settings import MCPConfig


class _FakeMCPManager:
    """模拟 MCPClientManager：暴露 session()/call_tool() 但不依赖真实 SDK。"""

    def __init__(self) -> None:
        self._calls: list[tuple[str, str, dict]] = []

    def session(self, server_name: str):
        return None  # adapter 只会在降级分支用 session，优先走 registry

    def server_names(self) -> list[str]:
        return ["fs"]

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        self._calls.append((server_name, tool_name, args))
        return {"ok": True, "echo": args, "server": server_name, "tool": tool_name}


def test_mcp_to_langchain_tools_fallback_wraps_each_tool():
    fake = _FakeMCPManager()
    reg = ToolRegistry(MCPConfig(emit_tool_events=False))
    reg.register_many(
        "fs",
        [
            type("T", (), {"name": "read", "description": "read file", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}),
            type("T", (), {"name": "write", "description": "write file", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}),
        ],
    )

    # 用真 MCPClientManager 的 type 但注入我们的 fake
    # adapter 接受 MCPClientManager 类型；这里直接传 fake（Protocol-typed）
    tools = mcp_to_langchain_tools(fake, reg)  # type: ignore[arg-type]

    # 官方 adapter 不存在/失败 -> 走降级包装
    assert len(tools) == 2
    assert all(isinstance(t, BaseTool) for t in tools)
    names = sorted(t.name for t in tools)
    assert names == ["fs:read", "fs:write"]


def test_mcp_to_langchain_tools_empty_registry_returns_empty():
    fake = _FakeMCPManager()
    reg = ToolRegistry(MCPConfig())
    tools = mcp_to_langchain_tools(fake, reg)  # type: ignore[arg-type]
    assert tools == []


def test_fallback_tool_invoke_calls_manager():
    async def _run():
        fake = _FakeMCPManager()
        reg = ToolRegistry(MCPConfig(emit_tool_events=False))
        reg.register_many(
            "fs",
            [
                type("T", (), {"name": "read", "description": "read file", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}),
            ],
        )
        tools = mcp_to_langchain_tools(fake, reg)  # type: ignore[arg-type]
        result = await tools[0].ainvoke({"path": "/tmp/x"})
        assert result == {
            "ok": True,
            "echo": {"path": "/tmp/x"},
            "server": "fs",
            "tool": "read",
        }
        assert fake._calls == [("fs", "read", {"path": "/tmp/x"})]

    asyncio.run(_run())
