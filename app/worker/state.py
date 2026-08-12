"""State Manager：负责 Agent 运行时状态的加载/快照/恢复。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage

from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis
from app.models.agent_state import AgentState

_log = get_logger(__name__)


def _msg_to_dict(m: Any) -> Any:
    """将 LangChain Message 对象转为可 JSON 序列化的 dict。

    astream 产出的 node_state["messages"] 是 BaseMessage 实例
    （HumanMessage/AIMessage 等），无法直接 json.dumps。这里用
    model_dump() 保留 type/content/tool_calls 等字段；load 回来后
    交给 add_messages reducer 可正确重建为 Message 对象。
    """
    if isinstance(m, BaseMessage):
        # pydantic v2 优先；兼容旧版 pydantic v1 的 .dict()
        if hasattr(m, "model_dump"):
            return m.model_dump()
        return m.dict()  # type: ignore[no-any-return]
    return m


class StateManager:
    """将 LangGraph state 序列化到 Redis，便于 worker 崩溃后恢复。"""

    def __init__(self, redis: RedisManager | None = None) -> None:
        self._redis = redis or get_redis()

    def _key(self, task_id: str) -> str:
        return f"mj:agent_state:{task_id}"

    async def save(self, task_id: str, state: AgentState) -> None:
        # 转换 TypedDict 为可序列化对象
        payload = {
            "messages": [_msg_to_dict(m) for m in state.get("messages", [])],
            "scratchpad": state.get("scratchpad", {}),
            "tool_results": state.get("tool_results", []),
            "tool_calls": state.get("tool_calls", []),
            "metadata": state.get("metadata", {}),
            "task_id": state.get("task_id", task_id),
            "game_id": state.get("game_id", ""),
            "iter": state.get("iter", 0),
            "game_state": state.get("game_state"),
        }
        await self._redis.kv_set(self._key(task_id), payload, ttl=24 * 3600)

    async def load(self, task_id: str) -> AgentState | None:
        data = await self._redis.kv_get(self._key(task_id))
        if not data:
            return None
        return AgentState(
            messages=data.get("messages", []),
            scratchpad=data.get("scratchpad", {}),
            tool_results=data.get("tool_results", []),
            tool_calls=data.get("tool_calls", []),
            metadata=data.get("metadata", {}),
            task_id=data.get("task_id", task_id),
            game_id=data.get("game_id", ""),
            iter=data.get("iter", 0),
            game_state=data.get("game_state"),
        )

    async def clear(self, task_id: str) -> None:
        await self._redis.client.delete(self._key(task_id))
