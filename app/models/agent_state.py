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
    - tool_results:   工具调用结果
    - metadata:       业务元数据透传
    - task_id:        任务 ID（用于事件归属）
    - iter:           循环迭代计数
    """

    messages: Annotated[list[AgentMessage], add_messages]
    scratchpad: dict[str, Any]
    tool_results: list[dict[str, Any]]
    metadata: dict[str, Any]
    task_id: str
    iter: int
