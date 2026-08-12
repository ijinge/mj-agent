"""模型 token 到业务事件的真实流式传递测试。"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.models.event import EventType
from app.worker.agent import build_default_graph, run_agent


class _RecordingAggregator:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue(self, event: Any) -> None:
        self.events.append(event)


class _StateManager:
    async def load(self, _task_id: str):
        return None

    async def save(self, _task_id: str, _state: Any) -> None:
        return None


async def test_run_agent_emits_incremental_model_tokens_without_full_duplicate() -> None:
    model = FakeListChatModel(responses=["流式回答"])
    graph = build_default_graph(llm=model)
    aggregator = _RecordingAggregator()

    async for _ in run_agent(
        task_id="stream-task",
        prompt="测试",
        aggregator=aggregator,  # type: ignore[arg-type]
        state_manager=_StateManager(),  # type: ignore[arg-type]
        graph=graph,
    ):
        pass

    tokens = [event.data["text"] for event in aggregator.events if event.type == EventType.TOKEN]
    assert tokens == ["流", "式", "回", "答"]
    assert "".join(tokens) == "流式回答"

    event_types = [event.type for event in aggregator.events]
    assert event_types[0] == EventType.STARTED
    assert event_types[-1] == EventType.FINISHED
