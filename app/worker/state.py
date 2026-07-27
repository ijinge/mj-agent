"""State Manager：负责 Agent 运行时状态的加载/快照/恢复。"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis
from app.models.agent_state import AgentState

_log = get_logger(__name__)


class StateManager:
    """将 LangGraph state 序列化到 Redis，便于 worker 崩溃后恢复。"""

    def __init__(self, redis: RedisManager | None = None) -> None:
        self._redis = redis or get_redis()

    def _key(self, task_id: str) -> str:
        return f"mj:agent_state:{task_id}"

    async def save(self, task_id: str, state: AgentState) -> None:
        # 转换 TypedDict 为可序列化对象
        payload = {
            "messages": list(state.get("messages", [])),
            "scratchpad": state.get("scratchpad", {}),
            "tool_results": state.get("tool_results", []),
            "tool_calls": state.get("tool_calls", []),
            "metadata": state.get("metadata", {}),
            "task_id": state.get("task_id", task_id),
            "iter": state.get("iter", 0),
        }
        await self._redis.kv_set(self._key(task_id), payload, ttl=24 * 3600)

    async def load(self, task_id: str) -> Optional[AgentState]:
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
            iter=data.get("iter", 0),
        )

    async def clear(self, task_id: str) -> None:
        await self._redis.client.delete(self._key(task_id))
