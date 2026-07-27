"""SSE 连接管理：注册、心跳、断开清理。"""
from __future__ import annotations

import asyncio
from typing import Optional

from app.common.ids import new_connection_id
from app.common.logger import get_logger

_log = get_logger(__name__)


class ConnectionRecord:
    __slots__ = ("connection_id", "task_id", "created_at", "last_heartbeat_at", "close_evt")

    def __init__(self, task_id: str) -> None:
        self.connection_id = new_connection_id()
        self.task_id = task_id
        self.created_at = asyncio.get_event_loop().time()
        self.last_heartbeat_at = self.created_at
        self.close_evt = asyncio.Event()


class ConnectionManager:
    def __init__(self, *, max_idle_seconds: float = 90.0) -> None:
        self._conns: dict[str, ConnectionRecord] = {}
        self._max_idle = max_idle_seconds
        self._lock = asyncio.Lock()

    async def register(self, task_id: str) -> ConnectionRecord:
        async with self._lock:
            rec = ConnectionRecord(task_id=task_id)
            self._conns[rec.connection_id] = rec
            _log.debug("sse register task_id=%s conn_id=%s", task_id, rec.connection_id)
            return rec

    async def unregister(self, connection_id: str) -> None:
        async with self._lock:
            rec = self._conns.pop(connection_id, None)
        if rec:
            rec.close_evt.set()
            _log.debug("sse unregister conn_id=%s", connection_id)

    async def touch(self, connection_id: str) -> None:
        async with self._lock:
            rec = self._conns.get(connection_id)
            if rec is not None:
                rec.last_heartbeat_at = asyncio.get_event_loop().time()

    async def close_all(self) -> None:
        async with self._lock:
            recs = list(self._conns.values())
            self._conns.clear()
        for r in recs:
            r.close_evt.set()

    async def idle_seconds(self, connection_id: str) -> Optional[float]:
        async with self._lock:
            rec = self._conns.get(connection_id)
            if rec is None:
                return None
            return asyncio.get_event_loop().time() - rec.last_heartbeat_at

    async def gc(self) -> int:
        """清理空闲超时的连接。"""
        now = asyncio.get_event_loop().time()
        stale: list[str] = []
        async with self._lock:
            for cid, rec in self._conns.items():
                if now - rec.last_heartbeat_at > self._max_idle:
                    stale.append(cid)
        for cid in stale:
            await self.unregister(cid)
        return len(stale)
