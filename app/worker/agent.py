"""LangGraph 循环入口（接入 MCP 工具）。

- build_default_graph: 构造 StateGraph
  - chat 节点：调 LLM（绑定 MCP 工具）
  - tools 节点：ToolNode（执行 MCP 工具调用）
  - 条件边：有 tool_calls -> tools，否则 END
- run_agent: 异步执行 agent 并产出事件
- create_llm: 按 Settings 创建 LangChain ChatModel

未配置 MCP 时，graph 退化为单 chat 节点（无 tool 边）。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Callable, Optional

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.common.logger import get_logger
from app.models.agent_state import AgentState
from app.models.event import Event, EventType
from app.worker.event_aggregator import EventAggregator
from app.worker.state import StateManager
from config.settings import LLMConfig

_log = get_logger(__name__)


# ---- LLM 工厂 ----
def create_llm(cfg: LLMConfig):
    """按 LLMConfig 构造 LangChain ChatModel。

    支持 openai / anthropic / ollama；缺依赖会抛 ImportError。
    """
    provider = cfg.provider.lower()
    common: dict[str, Any] = {"temperature": cfg.temperature}
    if cfg.max_tokens is not None:
        common["max_tokens"] = cfg.max_tokens

    if provider == "openai":
        from langchain_openai import ChatOpenAI  # type: ignore
        kwargs = {**common, "model": cfg.model}
        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # type: ignore
        kwargs = {**common, "model": cfg.model}
        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        return ChatAnthropic(**kwargs)

    if provider == "ollama":
        from langchain_openai import ChatOpenAI  # type: ignore
        # ollama 兼容 openai 接口
        kwargs = {
            **common,
            "model": cfg.model,
            "base_url": cfg.base_url or "http://localhost:11434/v1",
            "api_key": cfg.api_key or "ollama",
        }
        return ChatOpenAI(**kwargs)

    raise ValueError(f"unsupported LLM provider: {cfg.provider}")


# ---- Graph 构造 ----
def build_default_graph(
    *,
    llm: Any | None = None,
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """构造 LangGraph StateGraph。

    - 无 tools / llm：使用占位 chat 节点（用于本地开发/无 LLM 场景）
    - 有 llm 但无 tools：单 chat 节点 -> END
    - 有 llm + tools：chat -> (有 tool_calls ? tools -> chat : END)
    """
    g = StateGraph(AgentState)

    if llm is None:
        # 占位实现：echo
        async def _chat(state: AgentState) -> AgentState:
            msgs = list(state.get("messages", []))
            last = msgs[-1].get("content", "") if msgs else ""
            msgs.append({"role": "assistant", "content": f"echo: {last}"})
            return {
                **state,
                "messages": msgs,
                "iter": state.get("iter", 0) + 1,
            }
        g.add_node("chat", _chat)
        g.set_entry_point("chat")
        g.add_edge("chat", END)
        return g.compile()

    sys_text = system_prompt or "你是一个有工具调用能力的 Agent。"
    if tools:
        from langgraph.prebuilt import ToolNode  # 复用 LangGraph 原生
        llm_bound = llm.bind_tools(tools)

        def _chat(state: AgentState) -> AgentState:
            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
            msgs_in = state.get("messages", [])
            converted: list[Any] = [SystemMessage(content=sys_text)]
            for m in msgs_in:
                role = m.get("role") if isinstance(m, dict) else None
                content = m.get("content") if isinstance(m, dict) else m.content
                if role == "user":
                    converted.append(HumanMessage(content=content))
                elif role == "assistant":
                    converted.append(AIMessage(content=content, tool_calls=m.get("tool_calls")))
                else:
                    converted.append(HumanMessage(content=str(content)))
            ai = llm_bound.invoke(converted)
            new_msgs = list(msgs_in) + [{"role": "assistant", "content": ai.content, "tool_calls": getattr(ai, "tool_calls", None) or []}]
            return {
                **state,
                "messages": new_msgs,
                "tool_calls": getattr(ai, "tool_calls", None) or [],
                "iter": state.get("iter", 0) + 1,
            }

        def _should_call_tools(state: AgentState) -> str:
            tcs = state.get("tool_calls") or []
            if state.get("iter", 0) > 20:
                return END
            return "tools" if tcs else END

        tool_node = ToolNode(tools=tools, handle_tool_errors=True)
        g.add_node("chat", _chat)
        g.add_node("tools", tool_node)
        g.set_entry_point("chat")
        g.add_conditional_edges("chat", _should_call_tools, {"tools": "tools", END: END})
        g.add_edge("tools", "chat")
        return g.compile()

    # 无 tools：单 chat 节点
    def _chat(state: AgentState) -> AgentState:
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        msgs_in = state.get("messages", [])
        converted: list[Any] = [SystemMessage(content=sys_text)]
        for m in msgs_in:
            role = m.get("role") if isinstance(m, dict) else None
            content = m.get("content") if isinstance(m, dict) else m.content
            if role == "user":
                converted.append(HumanMessage(content=content))
            elif role == "assistant":
                converted.append(AIMessage(content=content))
            else:
                converted.append(HumanMessage(content=str(content)))
        ai = llm.invoke(converted)
        new_msgs = list(msgs_in) + [{"role": "assistant", "content": ai.content}]
        return {
            **state,
            "messages": new_msgs,
            "iter": state.get("iter", 0) + 1,
        }

    g.add_node("chat", _chat)
    g.set_entry_point("chat")
    g.add_edge("chat", END)
    return g.compile()


# ---- 执行 ----
async def run_agent(
    task_id: str,
    prompt: str,
    *,
    aggregator: EventAggregator,
    state_manager: StateManager,
    graph: CompiledStateGraph | None = None,
    max_iters: int = 10,
    on_event: Optional[Callable[[Event], None]] = None,
) -> AsyncIterator[Event]:
    """执行一个任务，异步产出事件。

    流程：
    1. started 事件
    2. 调用 graph.astream（chat 节点可能产生 token / tool_call）
    3. finished 事件
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

    state = await state_manager.load(task_id) or AgentState(
        messages=[{"role": "user", "content": prompt}],
        scratchpad={},
        tool_results=[],
        tool_calls=[],
        metadata={},
        task_id=task_id,
        iter=0,
    )
    state["task_id"] = task_id

    g = graph or build_default_graph()
    try:
        # 用 astream 拿到每个节点输出
        async for chunk in g.astream(state):
            for node_name, node_state in chunk.items():
                # 把每步内容作为 token 事件
                msgs = node_state.get("messages", []) if isinstance(node_state, dict) else []
                last = msgs[-1] if msgs else None
                text = ""
                if isinstance(last, dict):
                    text = last.get("content", "") or ""
                else:
                    text = getattr(last, "content", "") or ""
                tcs = node_state.get("tool_calls") if isinstance(node_state, dict) else None
                tok = Event(
                    event_id="",
                    task_id=task_id,
                    type=EventType.TOKEN,
                    data={"text": str(text)[:512], "node": node_name, "tool_calls": tcs or []},
                    seq=0,
                    created_at_ms=int(time.time() * 1000),
                )
                await aggregator.enqueue(tok)
                if on_event:
                    on_event(tok)
                await state_manager.save(task_id, node_state)
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
