"""LangGraph ToolNode 包装。

把 LangChain 工具列表构造为 LangGraph 的 `ToolNode`，
并提供在工具执行前后下发事件的钩子（TOOL_CALL / TOOL_RESULT）。
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from app.common.logger import get_logger
from app.models.event import Event, EventType
from app.worker.event_aggregator import EventAggregator

_log = get_logger(__name__)


def build_tool_node(
    tools: list[Any],
    *,
    aggregator: EventAggregator | None = None,
    task_id_getter: Callable[[], str] | None = None,
):
    """构造一个 LangGraph ToolNode 并注入事件钩子。

    - tools: LangChain 工具列表（来自 mcp_to_langchain_tools）
    - aggregator: 用于写 TOOL_CALL / TOOL_RESULT 事件；为 None 时跳过事件
    - task_id_getter: 提供当前 task_id（用于事件归属）

    返回：可被 LangGraph graph.add_node("tools", node) 直接使用的 node 函数。
    """
    from langgraph.prebuilt import ToolNode

    base = ToolNode(tools=tools, handle_tool_errors=True)

    if aggregator is None:
        return base  # 纯 ToolNode，不写事件

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        # 取 task_id：state.task_id 或通过 getter
        tid = state.get("task_id") if isinstance(state, dict) else None
        if not tid and task_id_getter is not None:
            tid = task_id_getter()

        # 取最后一条消息的 tool_calls 作为预上报
        msgs = state.get("messages", []) if isinstance(state, dict) else []
        last = msgs[-1] if msgs else None
        tool_calls = []
        if last is not None:
            tool_calls = getattr(last, "tool_calls", None) or []

        for tc in tool_calls:
            ev = Event(
                event_id="",
                task_id=tid or "",
                type=EventType.TOOL_CALL,
                data={
                    "name": tc.get("name"),
                    "args": tc.get("args"),
                    "id": tc.get("id"),
                },
                seq=0,
                created_at_ms=_now_ms(),
            )
            try:
                await aggregator.enqueue(ev)
            except Exception:  # noqa: BLE001
                _log.exception("emit TOOL_CALL event failed")

        # 执行真实工具
        result = await base.ainvoke(state)

        # 上报每条工具结果
        new_msgs = result.get("messages", []) if isinstance(result, dict) else []
        for m in new_msgs:
            name = getattr(m, "name", None) or "tool"
            content = getattr(m, "content", None)
            tool_call_id = getattr(m, "tool_call_id", None)
            ev = Event(
                event_id="",
                task_id=tid or "",
                type=EventType.TOOL_RESULT,
                data={
                    "name": name,
                    "tool_call_id": tool_call_id,
                    "content": _content_to_jsonable(content),
                },
                seq=0,
                created_at_ms=_now_ms(),
            )
            try:
                await aggregator.enqueue(ev)
            except Exception:  # noqa: BLE001
                _log.exception("emit TOOL_RESULT event failed")

        return result

    return _node


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


def _content_to_jsonable(content: Any) -> Any:
    """ToolMessage.content 可能是 str 或 list[dict]（多模态）。"""
    if isinstance(content, str):
        return content
    try:
        # 尝试 JSON 序列化
        import json
        return json.loads(json.dumps(content, default=str, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        return str(content)
