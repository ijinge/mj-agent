"""MCP client manager 单元测试（无真实 MCP server）。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.mcp.client import MCPClientManager
from config.settings import MCPServerConfig


def _stdio_cfg(name: str = "fs") -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        transport="stdio",
        command="echo",
        args=["hello"],
    )


def _sse_cfg(name: str = "remote", url: str = "http://localhost:9999/sse") -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        transport="sse",
        url=url,
        headers={"X-Test": "1"},
    )


def _http_cfg(name: str = "http", url: str = "http://localhost:9999/mcp") -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        transport="streamable_http",
        url=url,
    )


def test_filter_disabled_servers():
    mgr = MCPClientManager([
        _stdio_cfg("a"),
        MCPServerConfig(name="b", transport="stdio", enabled=False, command="x"),
    ])
    assert [s.name for s in mgr._servers] == ["a"]


def test_unsupported_transport_raises():
    bad = MCPServerConfig(name="x", transport="bogus", command="x")
    mgr = MCPClientManager([bad])
    async def _run():
        try:
            await mgr._connect_one(bad)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "unsupported" in str(e).lower()
    asyncio.run(_run())


def test_stdio_missing_command_raises():
    bad = MCPServerConfig(name="x", transport="stdio", command=None)
    mgr = MCPClientManager([bad])
    async def _run():
        try:
            await mgr._connect_stdio(bad)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "command" in str(e)
    asyncio.run(_run())


def test_sse_missing_url_raises():
    bad = MCPServerConfig(name="x", transport="sse", url=None)
    mgr = MCPClientManager([bad])
    async def _run():
        try:
            await mgr._connect_sse(bad)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "url" in str(e)
    asyncio.run(_run())


def test_session_lookup_after_connect_with_mocked_mcp():
    """完整 mock mcp SDK 验证 connect/session 行为。"""
    fake_session = MagicMock(name="ClientSession")
    fake_session.initialize = AsyncMock()

    @asynccontextmanager
    async def _fake_stdio_client(params):
        yield (MagicMock(), MagicMock())

    @asynccontextmanager
    async def _fake_session_cm(read, write):
        yield fake_session

    with patch.dict("sys.modules", {
        "mcp": MagicMock(ClientSession=lambda r, w: _fake_session_cm(r, w)),
        "mcp.client.stdio": MagicMock(
            stdio_client=_fake_stdio_client,
            StdioServerParameters=lambda **kw: object(),
        ),
    }):
        mgr = MCPClientManager([_stdio_cfg("fs")])
        asyncio.run(mgr.connect())
        try:
            assert "fs" in mgr.server_names()
            s = mgr.session("fs")
            assert s is fake_session
            fake_session.initialize.assert_awaited()
        finally:
            asyncio.run(mgr.aclose())
