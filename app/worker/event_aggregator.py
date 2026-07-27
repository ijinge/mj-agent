"""事件聚合器：把高频小事件（如 token）批量写入 Redis Stream，兼顾时延与吞吐。"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Optional

from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis
from app.models.event import Event, EventType

_log = get_logger(__name__)

# 事件类型可以聚合的（多 token 合并等）
AGGREGATABLE: frozenset[EventType] = frozenset({EventType.TOKEN, EventType.PROGRESS})


class EventAggregator:
    """按 task_id 维护事件缓冲：

    - 入队：enqueue(event)
    - 刷新条件：缓冲条数 >= max_batch OR 距离上次刷新 >= flush_interval_ms
    - 不可聚合事件（message/tool_call 等）立即刷新
    """

    def __init__(
        self,
        *,
        max_batch: int = 16,
        flush_interval_ms: int = 50,
        redis: RedisManager | None = None,
    ) -> None:
        self._max_batch = max_batch
        self._flush_interval = flush_interval_ms / 1000.0
        self._redis = redis or get_redis()
        self._buffers: dict[str, Deque[Event]] = {}
        self._last_flush_at: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._stop_evt = asyncio.Event()

    async def start(self) -> None:
        if self._flush_task is not None:
            return
        self._stop_evt.clear()
        self._flush_task = asyncio.create_task(self._periodic_flush(), name="event-aggregator")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._flush_task is not None:
            await self._flush_task
            self._flush_task = None
        # 收尾 flush
        await self.flush_all()

    async def enqueue(self, event: Event) -> None:
        if event.type not in AGGREGATABLE:
            # 不可聚合事件：直接写入
            await self._redis.xadd_event(event.task_id, event.model_dump())
            return
        async with self._lock:
            buf = self._buffers.setdefault(event.task_id, deque())
            buf.append(event)
            self._last_flush_at.setdefault(event.task_id, time.monotonic())
            if len(buf) >= self._max_batch:
                await self._flush_locked(event.task_id)

    async def _periodic_flush(self) -> None:
        try:
            while not self._stop_evt.is_set():
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=self._flush_interval)
                except asyncio.TimeoutError:
                    pass
                await self.flush_all()
        except asyncio.CancelledError:
            raise

    async def flush_all(self) -> None:
        async with self._lock:
            now = time.monotonic()
            to_flush = [
                tid
                for tid, ts in self._last_flush_at.items()
                if self._buffers.get(tid) and now - ts >= self._flush_interval
            ]
            for tid in to_flush:
                await self._flush_locked(tid)

    async def _flush_locked(self, task_id: str) -> None:
        buf = self._buffers.get(task_id)
        if not buf:
            return
        events = list(buf)
        buf.clear()
        self._last_flush_at[task_id] = time.monotonic()
        if len(events) == 1:
            await self._redis.xadd_event(task_id, events[0].model_dump())
            return
        # 同类型 token/progress 合并为单条聚合事件
        first = events[0]
        if first.type == EventType.TOKEN:
            merged = Event(
                event_id=first.event_id,
                task_id=task_id,
                type=EventType.TOKEN,
                data={"text": "".join(e.data.get("text", "") for e in events), "count": len(events)},
                seq=first.seq,
                created_at_ms=first.created_at_ms,
            )
            await self._redis.xadd_event(task_id, merged.model_dump())
        else:
            for e in events:
                await self._redis.xadd_event(task_id, e.model_dump())
