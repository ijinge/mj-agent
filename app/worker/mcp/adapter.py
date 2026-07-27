"""MCP 工具 → LangChain 工具 适配层。

优先使用官方 `langchain-mcp-adapters` 的 `load_mcp_tools`；
不可用时回退到本地手写包装（直接用 ClientSession.call_tool）。
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from langchain_core.tools import BaseTool

from app.common.logger import get_logger
from app.worker.mcp.client import MCPClientManager
from app.worker.mcp.registry import ToolDescriptor

_log = get_logger(__name__)


def _try_load_mcp_tools(session: Any) -> Optional[list[BaseTool]]:
    """尝试用 langchain-mcp-adapters 加载工具；失败返回 None。"""
    try:
        from langchain_mcp_adapters.tools import load_mcp_tools  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        tools = load_mcp_tools(session)
        return list(tools)
    except Exception:  # noqa: BLE001
        _log.exception("load_mcp_tools failed; fallback to manual adapter")
        return None


def _wrap_one(
    descriptor: ToolDescriptor,
    mgr: MCPClientManager,
) -> BaseTool:
    """把单个 MCP 工具包装成 LangChain StructuredTool。

    StructuredTool 会按 args_schema 自动校验和解析输入，
    然后把字段作为关键字参数传给 coroutine。
    """
    from langchain_core.tools import StructuredTool

    args_schema = _build_args_schema(descriptor.input_schema)

    async def _acall(**kwargs: Any) -> Any:
        # 仅保留 args_schema 中声明的字段，防止 LangChain 注入 run_id/config 等
        clean = _filter_kwargs(kwargs, descriptor.input_schema)
        return await mgr.call_tool(
            descriptor.server_name,
            descriptor.tool_name,
            clean,
        )

    def _call(**kwargs: Any) -> Any:
        import asyncio
        clean = _filter_kwargs(kwargs, descriptor.input_schema)
        return asyncio.run(
            mgr.call_tool(
                descriptor.server_name,
                descriptor.tool_name,
                clean,
            )
        )

    return StructuredTool.from_function(
        coroutine=_acall,
        func=_call,
        name=descriptor.qualified_name,
        description=descriptor.description or descriptor.tool_name,
        args_schema=args_schema,
    )


def _filter_kwargs(kwargs: dict[str, Any], input_schema: dict[str, Any]) -> dict[str, Any]:
    """只保留 args_schema 中声明的属性名。"""
    props = (input_schema or {}).get("properties", {}) or {}
    return {k: v for k, v in kwargs.items() if k in props}


def _build_args_schema(input_schema: dict[str, Any]):
    """把 JSON schema 转 pydantic（用于 LangChain Tool 的 args_schema）。"""
    try:
        from pydantic import BaseModel, Field, create_model

        properties = (input_schema or {}).get("properties", {}) or {}
        required = set((input_schema or {}).get("required", []) or [])

        fields: dict[str, Any] = {}
        for prop_name, prop_schema in properties.items():
            desc = prop_schema.get("description", "")
            typ = _json_type_to_python(prop_schema.get("type", "string"))
            default = ... if prop_name in required else None
            fields[prop_name] = (typ, Field(default=default, description=desc))

        if not fields:
            class _Empty(BaseModel):
                pass
            return _Empty

        return create_model(f"{descriptor_safe_name(input_schema)}Args", **fields)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return None


def descriptor_safe_name(schema: dict[str, Any]) -> str:
    title = (schema or {}).get("title") or "Args"
    return "".join(ch for ch in title if ch.isalnum() or ch == "_") or "Args"


def _json_type_to_python(t: str) -> Any:
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }.get(t, str)


def mcp_to_langchain_tools(
    mgr: MCPClientManager,
    registry,
) -> list[BaseTool]:
    """统一入口：把 MCP 工具桥接为 LangChain 工具列表。

    - 如果 langchain-mcp-adapters 可用且 mgr.session 正常 → 用其工具（保留原始 schema）
    - 否则按 registry 注册的描述手写包装（兼容 + 降级）
    """
    tools: list[BaseTool] = []
    descriptors = registry.all() if hasattr(registry, "all") else []
    if not descriptors:
        return tools

    # 尝试官方 adapter（每个 server 一次）
    by_server: dict[str, list[ToolDescriptor]] = {}
    for d in descriptors:
        by_server.setdefault(d.server_name, []).append(d)

    used_official = False
    try:
        for server_name in by_server.keys():
            session = mgr.session(server_name)
            if session is None:
                continue
            official = _try_load_mcp_tools(session)
            if not official:
                continue
            # 官方工具可能使用原始 tool_name；我们重新映射为 qualified name
            for t in official:
                try:
                    t.name = f"{server_name}:{t.name}"  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
            tools.extend(official)
            used_official = True
    except Exception:  # noqa: BLE001
        _log.exception("official adapter path failed; using manual wrapper")

    if used_official:
        return tools

    # 降级：手写包装
    for d in descriptors:
        try:
            tools.append(_wrap_one(d, mgr))
        except Exception:  # noqa: BLE001
            _log.exception("wrap tool failed name=%s", d.qualified_name)
    return tools
