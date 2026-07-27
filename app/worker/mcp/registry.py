"""Tool Registry：聚合 MCP 工具，提供命名空间查找。

工具全名约定：`<server_name>:<tool_name>`
- 原始 MCP tool_name 可能与不同 server 撞名，统一加 server 前缀避免冲突
- 提供 allowlist / denylist 过滤
- 提供按 server / 全量两种列举
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.common.logger import get_logger
from config.settings import MCPConfig

_log = get_logger(__name__)


@dataclass
class ToolDescriptor:
    """注册表中的工具描述（与 MCP tool 解耦，适配 LangChain tool）。"""

    server_name: str          # 原始 server 名
    tool_name: str            # 原始 tool 名
    qualified_name: str       # `<server>:<tool>` 全限定名
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    raw: Any = None           # 原始 mcp Tool 对象

    def short_repr(self) -> str:
        return f"{self.qualified_name} ({self.server_name})"


class ToolRegistry:
    def __init__(self, config: MCPConfig | None = None) -> None:
        self._config = config or MCPConfig()
        self._items: dict[str, ToolDescriptor] = {}

    # ---- 注册 ----
    def register(self, descriptor: ToolDescriptor) -> None:
        if not self._accept(descriptor):
            _log.debug("tool filtered out name=%s", descriptor.qualified_name)
            return
        self._items[descriptor.qualified_name] = descriptor
        _log.info("tool registered name=%s server=%s", descriptor.qualified_name, descriptor.server_name)

    def register_many(self, server_name: str, tools: Iterable[Any]) -> int:
        n = 0
        for t in tools:
            desc = self._to_descriptor(server_name, t)
            if desc is None:
                continue
            self.register(desc)
            n += 1
        return n

    def clear(self) -> None:
        self._items.clear()

    # ---- 查询 ----
    def get(self, qualified_name: str) -> Optional[ToolDescriptor]:
        return self._items.get(qualified_name)

    def all(self) -> list[ToolDescriptor]:
        return list(self._items.values())

    def by_server(self, server_name: str) -> list[ToolDescriptor]:
        return [t for t in self._items.values() if t.server_name == server_name]

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, qualified_name: object) -> bool:
        return qualified_name in self._items

    # ---- internals ----
    def _accept(self, desc: ToolDescriptor) -> bool:
        if self._config.denylist and desc.qualified_name in self._config.denylist:
            return False
        if self._config.allowlist and desc.qualified_name not in self._config.allowlist:
            return False
        return True

    def _to_descriptor(self, server_name: str, tool: Any) -> Optional[ToolDescriptor]:
        try:
            name = getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else None)
            if not name:
                return None
            desc = (
                getattr(tool, "description", "")
                or (tool.get("description", "") if isinstance(tool, dict) else "")
            )
            schema = (
                getattr(tool, "inputSchema", None)
                or getattr(tool, "input_schema", None)
                or (tool.get("inputSchema") if isinstance(tool, dict) else {})
                or {}
            )
            return ToolDescriptor(
                server_name=server_name,
                tool_name=name,
                qualified_name=f"{server_name}:{name}",
                description=desc or "",
                input_schema=schema,
                raw=tool,
            )
        except Exception:  # noqa: BLE001
            _log.exception("convert tool to descriptor failed server=%s tool=%s", server_name, tool)
            return None
