"""LangGraph ToolNode 包装。

把 LangChain 工具列表构造为 LangGraph 的 `ToolNode`，
并提供在工具执行前后下发事件的钩子（TOOL_CALL / TOOL_RESULT）。

game_state 占位符机制：
  LLM 在工具调用参数中传字符串 "__GAME_STATE__" 作为 game_state 值，
  tool_node 在执行工具前将其替换为 state["game_state"] 中的真实 JSON。
  这样 LLM 不需要看到完整的 game_state，只需传一个标记即可。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.common.logger import get_logger
from app.models.event import Event, EventType
from app.worker.event_aggregator import EventAggregator

_log = get_logger(__name__)

# LLM 在工具参数中传此字符串表示"请用真实的 game_state 替换"
GAME_STATE_PLACEHOLDER = "__GAME_STATE__"


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

        # 将 LLM 传入的 "__GAME_STATE__" 占位符替换为真实的 game_state
        run_state = _replace_game_state_placeholder(state)

        # 执行真实工具（2 秒超时）
        import asyncio
        try:
            result = await asyncio.wait_for(base.ainvoke(run_state), timeout=2.0)
        except asyncio.TimeoutError:
            _log.warning("tool call timed out after 2s")
            # 构造超时错误结果，让 graph 继续走 chat 节点
            from langchain_core.messages import ToolMessage
            timeout_msgs = []
            for tc in tool_calls:
                timeout_msgs.append(ToolMessage(
                    content="工具调用超时（2s），请重试或换一种方式。",
                    tool_call_id=tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None),
                    name=tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "tool"),
                ))
            result = {"messages": timeout_msgs}

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
    """ToolMessage.content 可能是 str、list[TextContent] 或 list[dict]（多模态）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # 处理 list[TextContent] / list[dict] 多模态内容
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                # TextContent 等 LangChain 对象
                text = getattr(item, "text", None)
                if text is not None:
                    parts.append(text)
                else:
                    parts.append(str(item))
        return "\n".join(parts) if parts else ""
    try:
        return json.loads(json.dumps(content, default=str, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        return str(content)


def _replace_game_state_placeholder(state: dict[str, Any]) -> dict[str, Any]:
    """将 LLM tool_calls 中的 __GAME_STATE__ 占位符替换为真实 game_state。

    LLM 在调用需要 game_state 的工具时，只需在参数中传字符串 "__GAME_STATE__"，
    本函数在执行工具前将其替换为 state["game_state"] 中的真实 JSON 对象。

    如果 state 中没有 game_state 或 tool_calls 中没有占位符，返回原 state。
    """
    game_state = state.get("game_state")
    if game_state is None:
        return state

    msgs = state.get("messages", []) if isinstance(state, dict) else []
    if not msgs:
        return state

    last = msgs[-1]
    tool_calls = (
        getattr(last, "tool_calls", None) if not isinstance(last, dict) else last.get("tool_calls")
    )
    if not tool_calls:
        return state

    # 检查是否有占位符需要替换
    has_placeholder = False
    for tc in tool_calls:
        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
        if (
            args
            and isinstance(args, dict)
            and any(v == GAME_STATE_PLACEHOLDER for v in args.values())
        ):
            has_placeholder = True
            break

    if not has_placeholder:
        return state

    # 构造替换后的 tool_calls
    new_tool_calls = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            args = dict(tc.get("args") or {})
            for k, v in args.items():
                if v == GAME_STATE_PLACEHOLDER:
                    args[k] = game_state
            new_tool_calls.append({**tc, "args": args})
        else:
            # BaseMessage 的 tool_calls 可能是对象列表
            args = getattr(tc, "args", None) or {}
            if isinstance(args, dict):
                new_args = {
                    k: (game_state if v == GAME_STATE_PLACEHOLDER else v) for k, v in args.items()
                }
                # 构造新的 tool_call 对象（保持原类型）
                tc_type = type(tc)
                if hasattr(tc_type, "model_copy"):
                    new_tc = tc.model_copy(update={"args": new_args})
                else:
                    new_tc = tc
                    new_tc.args = new_args
                new_tool_calls.append(new_tc)
            else:
                new_tool_calls.append(tc)

    # 构造新的 messages 列表（替换最后一条消息的 tool_calls）
    if isinstance(last, dict):
        new_last = {**last, "tool_calls": new_tool_calls}
    else:
        from langchain_core.messages import AIMessage

        content = getattr(last, "content", "") or ""
        new_last = AIMessage(content=content, tool_calls=new_tool_calls)

    return {**state, "messages": list(msgs[:-1]) + [new_last]}
