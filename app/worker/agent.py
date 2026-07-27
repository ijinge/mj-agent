"""LangGraph 循环入口。

提供：
- build_default_graph: 构造一个最小可运行的 LangGraph StateGraph
- run_agent:           异步执行 agent，产出事件

实际部署时可替换为自定义 graph / 工具节点 / 提示词工程。
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Callable, Optional

from langgraph.graph import END, StateGraph

from app.common.logger import get_logger
from app.models.agent_state import AgentState
from app.models.event import Event, EventType
from app.worker.event_aggregator import EventAggregator
from app.worker.state import StateManager

_log = get_logger(__name__)


# ---- 节点（示例） ----
async def _think_node(state: AgentState) -> AgentState:
    """思考节点：示例为把 prompt 写到 scratchpad。"""
    msgs = state.get("messages", [])
    prompt = msgs[-1].get("content", "") if msgs else ""
    scratch = dict(state.get("scratchpad", {}))
    scratch.setdefault("thoughts", []).append(f"received: {prompt!r}")
    return {**state, "scratchpad": scratch, "iter": state.get("iter", 0) + 1}


async def _answer_node(state: AgentState) -> AgentState:
    """回答节点：示例为回显 scratchpad。"""
    scratch = state.get("scratchpad", {})
    answer = f"echo: {scratch.get('thoughts', ['(empty)'])[-1]}"
    msgs = list(state.get("messages", []))
    msgs.append({"role": "assistant", "content": answer})
    return {**state, "messages": msgs}


def _should_continue(state: AgentState) -> str:
    if state.get("iter", 0) >= 1:
        return END
    return "answer"


def build_default_graph():
    """构造一个最小 LangGraph。"""
    g = StateGraph(AgentState)
    g.add_node("think", _think_node)
    g.add_node("answer", _answer_node)
    g.set_entry_point("think")
    g.add_conditional_edges("think", _should_continue, {"answer": "answer", END: END})
    g.add_edge("answer", END)
    return g.compile()


# ---- 执行 ----
async def run_agent(
    task_id: str,
    prompt: str,
    *,
    aggregator: EventAggregator,
    state_manager: StateManager,
    max_iters: int = 10,
    on_event: Optional[Callable[[Event], None]] = None,
) -> AsyncIterator[Event]:
    """执行一个任务，异步产出事件。

    流程：
    1. 写 started 事件
    2. 跑 LangGraph 循环
    3. 每步产生 token/finished 事件
    4. 状态保存到 Redis
    """
    started = Event(
        event_id="",
        task_id=task_id,
        type=EventType.STARTED,
        data={"prompt": prompt, "max_iters": max_iters},
        seq=0,
        created_at_ms=int(time.time() * 1000),
    )
    await aggregator.enqueue(started)
    if on_event:
        on_event(started)

    # 恢复/初始化 state
    state = await state_manager.load(task_id) or AgentState(
        messages=[{"role": "user", "content": prompt}],
        scratchpad={},
        tool_results=[],
        metadata={},
        task_id=task_id,
        iter=0,
    )

    graph = build_default_graph()
    try:
        # astream_events 让我们拿到节点级别的进度（生产可换成自定义回调）
        async for ev in graph.astream(state):
            # 简化：每个 step 产生一个 message 事件
            node_name = next(iter(ev.keys()))
            chunk = ev[node_name]
            token_event = Event(
                event_id="",
                task_id=task_id,
                type=EventType.TOKEN,
                data={"text": f"[{node_name}] ", "node": node_name},
                seq=0,
                created_at_ms=int(time.time() * 1000),
            )
            await aggregator.enqueue(token_event)
            if on_event:
                on_event(token_event)
            await state_manager.save(task_id, chunk)

        finished = Event(
            event_id="",
            task_id=task_id,
            type=EventType.FINISHED,
            data={"ok": True},
            seq=0,
            created_at_ms=int(time.time() * 1000),
        )
        await aggregator.enqueue(finished)
        if on_event:
            on_event(finished)
        yield finished
    except Exception as exc:  # noqa: BLE001
        err = Event(
            event_id="",
            task_id=task_id,
            type=EventType.ERROR,
            data={"message": str(exc)},
            seq=0,
            created_at_ms=int(time.time() * 1000),
        )
        await aggregator.enqueue(err)
        if on_event:
            on_event(err)
        raise
