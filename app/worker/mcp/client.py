"""MCP client manager。

负责管理多个 MCP server 连接：
- 按 transport 启动对应客户端（stdio 子进程 / sse / streamable_http）
- 初始化 ClientSession，调用 `initialize` + `list_tools`
- 维护 (server_name -> ClientSession) 映射
- 提供统一的 aclose 入口
"""
from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any, Optional

from app.common.logger import get_logger
from config.settings import MCPServerConfig

_log = get_logger(__name__)


class MCPClientManager:
    """多 MCP server 连接管理。

    使用方式：

        async with MCPClientManager(config) as mgr:
            tools = await mgr.list_all_tools()
            session = mgr.session("filesystem")
            result = await session.call_tool("read_file", {...})
    """

    def __init__(self, servers: list[MCPServerConfig]) -> None:
        self._servers = [s for s in servers if s.enabled]
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}    # server_name -> ClientSession
        self._tools_cache: dict[str, list[Any]] = {}  # server_name -> list of mcp Tool
        self._lock = asyncio.Lock()
        self._connected = False

    # ---- lifecycle ----
    async def __aenter__(self) -> "MCPClientManager":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def connect(self) -> None:
        if self._connected:
            return
        async with self._lock:
            if self._connected:
                return
            for cfg in self._servers:
                try:
                    await self._connect_one(cfg)
                except Exception:  # noqa: BLE001
                    _log.exception("MCP server connect failed name=%s transport=%s", cfg.name, cfg.transport)
            self._connected = True
            _log.info("MCP client connected servers=%s", list(self._sessions.keys()))

    async def aclose(self) -> None:
        if not self._connected:
            return
        try:
            await self._exit_stack.aclose()
        finally:
            self._sessions.clear()
            self._tools_cache.clear()
            self._connected = False
            _log.info("MCP client closed")

    # ---- public api ----
    def session(self, server_name: str) -> Any:
        if server_name not in self._sessions:
            raise KeyError(f"MCP server not connected: {server_name}")
        return self._sessions[server_name]

    def server_names(self) -> list[str]:
        return list(self._sessions.keys())

    async def list_tools(self, server_name: str) -> list[Any]:
        if server_name in self._tools_cache:
            return self._tools_cache[server_name]
        session = self.session(server_name)
        result = await session.list_tools()
        tools = list(result.tools) if hasattr(result, "tools") else list(result)
        self._tools_cache[server_name] = tools
        return tools

    async def list_all_tools(self) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for name in self.server_names():
            try:
                out[name] = await self.list_tools(name)
            except Exception:  # noqa: BLE001
                _log.exception("MCP list_tools failed server=%s", name)
        return out

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        session = self.session(server_name)
        return await session.call_tool(tool_name, arguments or {})

    # ---- internals ----
    async def _connect_one(self, cfg: MCPServerConfig) -> None:
        kind = cfg.transport_kind()
        if kind == "stdio":
            await self._connect_stdio(cfg)
        elif kind == "sse":
            await self._connect_sse(cfg)
        elif kind in {"streamable_http", "http"}:
            await self._connect_streamable_http(cfg)
        else:
            raise ValueError(f"unsupported MCP transport: {cfg.transport}")

    async def _connect_stdio(self, cfg: MCPServerConfig) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        if not cfg.command:
            raise ValueError(f"stdio MCP server '{cfg.name}' requires 'command'")
        env = {**os.environ, **(cfg.env or {})}
        params = StdioServerParameters(
            command=cfg.command,
            args=list(cfg.args or []),
            env=env,
            cwd=cfg.cwd,
        )
        read, write = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=cfg.connect_timeout_seconds)
        self._sessions[cfg.name] = session

    async def _connect_sse(self, cfg: MCPServerConfig) -> None:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        if not cfg.url:
            raise ValueError(f"sse MCP server '{cfg.name}' requires 'url'")
        read, write = await self._exit_stack.enter_async_context(
            sse_client(cfg.url, headers=cfg.headers or None)
        )
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=cfg.connect_timeout_seconds)
        self._sessions[cfg.name] = session

    async def _connect_streamable_http(self, cfg: MCPServerConfig) -> None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        if not cfg.url:
            raise ValueError(f"streamable_http MCP server '{cfg.name}' requires 'url'")
        read, write, _ = await self._exit_stack.enter_async_context(
            streamablehttp_client(cfg.url, headers=cfg.headers or None)
        )
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=cfg.connect_timeout_seconds)
        self._sessions[cfg.name] = session
