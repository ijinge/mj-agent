"""队列分发：将任务入队，供 worker 消费。"""
from __future__ import annotations

from typing import Any

from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis
from app.models.task import Task

_log = get_logger(__name__)


class TaskDispatcher:
    def __init__(self, queue: str, redis: RedisManager | None = None) -> None:
        self._queue = queue
        self._redis = redis or get_redis()

    async def dispatch(self, task: Task) -> int:
        payload: dict[str, Any] = {
            "task_id": task.task_id,
            "user_id": task.user_id,
            "prompt": task.prompt,
            "metadata": task.metadata,
        }
        n = await self._redis.enqueue(self._queue, payload)
        _log.info("task dispatched task_id=%s queue=%s depth=%s", task.task_id, self._queue, n)
        return n

    async def fetch(self, *, block_ms: int = 0) -> dict[str, Any] | None:
        return await self._redis.dequeue(self._queue, block_ms=block_ms)
