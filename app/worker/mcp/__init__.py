"""worker.mcp: Model Context Protocol 接入层。

负责：
- 连接管理：多 server / 多 transport（stdio / sse / streamable_http）
- 工具发现：聚合各 server 的工具列表
- 桥接：把 MCP 工具转换为 LangChain / LangGraph 工具
- 工具调用事件：把 call/result 通过 EventAggregator 下发

主要组件：
- config:     MCPConfig / MCPServerConfig（已由 config.settings 暴露）
- client:     MCPClientManager — 维护多个 ClientSession
- registry:   ToolRegistry      — 全局工具名空间与查找
- adapter:    mcp_to_langchain_tools — 转换工具 schema
- tool_node:  build_tool_node   — 构造 LangGraph ToolNode
"""
from app.worker.mcp.registry import ToolRegistry, ToolDescriptor
from app.worker.mcp.client import MCPClientManager
from app.worker.mcp.adapter import mcp_to_langchain_tools
from app.worker.mcp.tool_node import build_tool_node

__all__ = [
    "ToolRegistry",
    "ToolDescriptor",
    "MCPClientManager",
    "mcp_to_langchain_tools",
    "build_tool_node",
]
