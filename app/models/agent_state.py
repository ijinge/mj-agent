"""Agent 状态：LangGraph 内部 state + 消息历史。"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentMessage(TypedDict, total=False):
    """LangGraph 消息条目（兼容 langchain_core.messages 简化形态）。"""

    role: str
    content: str
    tool_call_id: str | None
    name: str | None


class AgentState(TypedDict, total=False):
    """LangGraph 共享 state。

    - messages:       消息历史（add_messages reducer 自动合并）
    - scratchpad:     Agent 内部草稿（推理、计划、变量）
    - tool_results:   工具调用结果（已合并的工具返回值）
    - tool_calls:     待执行的工具调用（来自 LLM 的 tool_calls）
    - metadata:       业务元数据透传
    - task_id:        任务 ID（用于事件归属）
    - game_id:        地方麻将类型 ID（与 MCP server name 精确匹配）
    - iter:           循环迭代计数
    - game_state:     场面信息 JSON（供 tool_node 替换占位符 "__GAME_STATE__"）
    """

    messages: Annotated[list[AgentMessage], add_messages]
    scratchpad: dict[str, Any]
    tool_results: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    metadata: dict[str, Any]
    task_id: str
    game_id: str
    iter: int
    game_state: Any
