"""LLM 调用工具后的消息回传回归测试。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app.models.agent_state import AgentState
from app.worker.agent import build_default_graph


class _FakeBoundLLM:
    def __init__(self) -> None:
        self.calls: list[list[Any]] = []

    async def astream(self, messages: list[Any]):
        self.calls.append(messages)
        if len(self.calls) == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": "mahjong_decision",
                        "args": '{"game_state":"__GAME_STATE__"}',
                        "id": "call-1",
                        "index": 0,
                    }
                ],
            )
            return
        for token in "建议打出九万。":
            yield AIMessageChunk(content=token)


class _FakeLLM:
    def __init__(self) -> None:
        self.bound = _FakeBoundLLM()

    def bind_tools(self, _tools: list[Any]) -> _FakeBoundLLM:
        return self.bound


async def _event_tool_node(state: AgentState) -> dict[str, Any]:
    call = state["messages"][-1].tool_calls[0]  # type: ignore[union-attr]
    return {
        "messages": [
            ToolMessage(
                content='{"discard":"9m"}',
                tool_call_id=call["id"],
                name=call["name"],
            )
        ]
    }


async def test_custom_tool_node_returns_tool_message_to_llm() -> None:
    llm = _FakeLLM()
    graph = build_default_graph(
        llm=llm,
        tools=[object()],
        tool_node=_event_tool_node,
    )
    result = await graph.ainvoke(
        AgentState(
            messages=[{"role": "user", "content": "现在打哪张？"}],
            tool_calls=[],
            game_id="ncmj-server",
            iter=0,
        )
    )

    assert result["messages"][-1].content == "建议打出九万。"
    second_call = llm.bound.calls[1]
    assert isinstance(second_call[-2], AIMessage)
    assert isinstance(second_call[-1], ToolMessage)
    assert second_call[-1].content == '{"discard":"9m"}'
    assert "ncmj-server" in llm.bound.calls[0][0].content
