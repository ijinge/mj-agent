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

import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import message_chunk_to_message
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.common.logger import get_logger
from app.models.agent_state import AgentState
from app.models.event import Event, EventType
from app.worker.event_aggregator import EventAggregator
from app.worker.json2cn import render as render_game_state
from app.worker.state import StateManager
from config.settings import LLMConfig

_log = get_logger(__name__)


# ---- 默认系统提示 ----
_PROMPT_PATH = Path(__file__).parent / "prompt.txt"
DEFAULT_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


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
    tool_node: Any | None = None,
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

    sys_text = system_prompt or DEFAULT_SYSTEM_PROMPT
    if tools:
        llm_bound = llm.bind_tools(tools)

        async def _chat(state: AgentState) -> AgentState:
            from langchain_core.messages import ToolMessage

            msgs_in = state.get("messages", [])
            converted = _to_llm_messages(
                msgs_in,
                _render_system_prompt(sys_text, state.get("game_state"), state.get("game_id", "")),
            )
            ai = await _stream_model_response(llm_bound, converted)

            final_content = ai.content or ""
            tcs = getattr(ai, "tool_calls", None) or []

            # 兜底：LLM 返回空内容 → 从工具结果中提取内容作为最终答案
            if not final_content and not tcs:
                tool_results = [m for m in converted if isinstance(m, ToolMessage)]
                if tool_results:
                    _log.info(
                        "LLM returned empty after tool result, using tool result as final answer"
                    )
                    final_content = _content_to_text(tool_results[-1].content)

            new_msgs = list(msgs_in) + [
                {"role": "assistant", "content": final_content, "tool_calls": tcs}
            ]
            return {
                **state,
                "messages": new_msgs,
                "tool_calls": tcs,
                "iter": state.get("iter", 0) + 1,
            }

        def _should_call_tools(state: AgentState) -> str:
            tcs = state.get("tool_calls") or []
            if state.get("iter", 0) >= 3:
                _log.warning("tool call retry limit reached (3), forcing END")
                return END
            return "tools" if tcs else END

        if tool_node is None:
            from langgraph.prebuilt import ToolNode

            tool_node = ToolNode(tools=tools, handle_tool_errors=True)
        g.add_node("chat", _chat)
        g.add_node("tools", tool_node)
        g.set_entry_point("chat")
        g.add_conditional_edges("chat", _should_call_tools, {"tools": "tools", END: END})
        g.add_edge("tools", "chat")
        return g.compile()

    # 无 tools：单 chat 节点
    async def _chat(state: AgentState) -> AgentState:
        msgs_in = state.get("messages", [])
        converted = _to_llm_messages(
            msgs_in,
            _render_system_prompt(sys_text, state.get("game_state"), state.get("game_id", "")),
        )
        ai = await _stream_model_response(llm, converted)
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


def _to_llm_messages(messages: list[Any], system_prompt: str) -> list[Any]:
    """保留 LangChain 消息类型，并兼容 Redis 恢复后的字典消息。"""
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )

    converted: list[Any] = [SystemMessage(content=system_prompt)]
    for message in messages:
        if isinstance(message, BaseMessage):
            converted.append(message)
            continue

        if not isinstance(message, dict):
            converted.append(HumanMessage(content=str(message)))
            continue

        message_type = message.get("role") or message.get("type")
        content = message.get("content", "")
        if message_type in {"user", "human"}:
            converted.append(HumanMessage(content=content))
        elif message_type in {"assistant", "ai"}:
            converted.append(AIMessage(content=content, tool_calls=message.get("tool_calls") or []))
        elif message_type == "tool":
            converted.append(
                ToolMessage(
                    content=content,
                    tool_call_id=message.get("tool_call_id") or "",
                    name=message.get("name"),
                )
            )
        elif message_type == "system":
            converted.append(SystemMessage(content=content))
        else:
            converted.append(HumanMessage(content=str(content)))
    return converted


def _system_prompt_with_game_id(system_prompt: str, game_id: str) -> str:
    if not game_id:
        return system_prompt
    return (
        f"{system_prompt.rstrip()}\n\n"
        "## 当前任务路由\n\n"
        f"地方麻将类型 ID：`{game_id}`。"
        "当前可见工具仅来自同名 MCP server。"
    )


def _render_system_prompt(system_prompt: str, game_state: Any, game_id: str) -> str:
    """渲染 system prompt，填入 game_state 和 game_id。"""
    # 先替换 {common_info}
    common_info = ""
    if game_state and isinstance(game_state, dict):
        try:
            common_info = render_game_state(game_state)
        except Exception as e:
            _log.warning(f"Failed to render game_state: {e}")

    prompt = system_prompt.replace("{common_info}", common_info)

    # 再添加 game_id 信息
    return _system_prompt_with_game_id(prompt, game_id)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text", "")))
            elif hasattr(item, "text"):
                texts.append(str(item.text))
        return "\n".join(texts) if texts else str(content)
    return str(content)


async def _stream_model_response(model: Any, messages: list[Any]) -> Any:
    """显式消费模型流并合并为 Graph 后续节点需要的完整 AIMessage。"""
    combined = None
    async for chunk in model.astream(messages):
        combined = chunk if combined is None else combined + chunk
    if combined is None:
        raise RuntimeError("LLM stream returned no chunks")
    return message_chunk_to_message(combined)


class _TokenStreamHandler(AsyncCallbackHandler):
    """把 LangChain 的模型增量回调转换为业务 TOKEN 事件。"""

    def __init__(
        self,
        *,
        task_id: str,
        aggregator: EventAggregator,
        on_event: Callable[[Event], None] | None,
    ) -> None:
        self._task_id = task_id
        self._aggregator = aggregator
        self._on_event = on_event
        self._current_chunks: list[str] = []

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        del kwargs
        if not token:
            return
        self._current_chunks.append(token)
        await self.emit(token)

    async def emit(self, text: str) -> None:
        event = Event(
            event_id="",
            task_id=self._task_id,
            type=EventType.TOKEN,
            data={"text": text, "node": "chat", "streaming": True},
            seq=0,
            created_at_ms=int(time.time() * 1000),
        )
        await self._aggregator.enqueue(event)
        if self._on_event:
            self._on_event(event)

    def take_current_text(self) -> str:
        text = "".join(self._current_chunks)
        self._current_chunks.clear()
        return text


# ---- 执行 ----
async def run_agent(
    task_id: str,
    prompt: str,
    *,
    aggregator: EventAggregator,
    state_manager: StateManager,
    graph: CompiledStateGraph | None = None,
    max_iters: int = 10,
    on_event: Callable[[Event], None] | None = None,
    game_id: str = "",
    game_state: Any | None = None,
) -> AsyncIterator[Event]:
    """执行一个任务，异步产出事件。

    流程：
    1. started 事件
    2. 调用 graph.astream（chat 节点可能产生 token / tool_call）
    3. finished 事件

    game_state: 任务对应的场面信息 JSON，写入 state["game_state"]，
    tool_node 在执行工具前会将 LLM 传入的 "__GAME_STATE__" 占位符替换为真实值。
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
        game_id=game_id,
        iter=0,
        game_state=game_state,
    )
    state["task_id"] = task_id
    state["game_id"] = game_id
    # 每次运行都用本次任务的 game_state 覆盖（断点续跑时旧值可能已过时）
    if game_state is not None:
        state["game_state"] = game_state

    g = graph or build_default_graph()
    stream_handler = _TokenStreamHandler(
        task_id=task_id,
        aggregator=aggregator,
        on_event=on_event,
    )
    try:
        # 用 astream 拿到每个节点输出
        async for chunk in g.astream(state, config={"callbacks": [stream_handler]}):
            for node_name, node_state in chunk.items():
                # 模型支持增量回调时，正文已经逐 token 发出；不支持时在节点完成后整段兜底。
                if node_name == "chat":
                    msgs = node_state.get("messages", []) if isinstance(node_state, dict) else []
                    last = msgs[-1] if msgs else None
                    text = ""
                    if isinstance(last, dict):
                        text = last.get("content", "") or ""
                    else:
                        text = getattr(last, "content", "") or ""
                    final_text = str(text)
                    streamed_text = stream_handler.take_current_text()
                    if final_text and not streamed_text:
                        await stream_handler.emit(final_text)
                    elif final_text.startswith(streamed_text):
                        missing_suffix = final_text[len(streamed_text) :]
                        if missing_suffix:
                            await stream_handler.emit(missing_suffix)
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
    except Exception as exc:
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
