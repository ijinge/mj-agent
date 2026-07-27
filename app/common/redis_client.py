"""异步 Redis 客户端封装。

设计要点：
- 全局单例 `redis_manager` 负责连接池生命周期
- 提供 stream / kv / counter 等常用高层 API
- key 命名空间集中管理，避免散落
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import redis.asyncio as redis
from redis.asyncio.client import PubSub

from app.common.logger import get_logger

_log = get_logger(__name__)


# ---- Key 命名空间 ----
def k_task(task_id: str) -> str:
    return f"mj:task:{task_id}"


def k_task_events_stream(task_id: str) -> str:
    return f"mj:task:{task_id}:events"


def k_task_event_seq(task_id: str) -> str:
    """任务内事件序号计数器。"""
    return f"mj:task:{task_id}:event_seq"


def k_queue(queue_name: str) -> str:
    return f"mj:queue:{queue_name}"


class RedisManager:
    """Redis 异步连接管理。"""

    def __init__(self, url: str, max_connections: int = 32) -> None:
        self._url = url
        self._max_connections = max_connections
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._pool = redis.ConnectionPool.from_url(
            self._url, max_connections=self._max_connections, decode_responses=True
        )
        self._client = redis.Redis(connection_pool=self._pool)
        # 触发一次连接以尽早暴露配置错误
        await self._client.ping()
        _log.info("redis connected url=%s", self._url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
        _log.info("redis closed")

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("RedisManager is not connected. Call connect() first.")
        return self._client

    # ---- 高级 API：流 ----
    async def xadd_event(self, task_id: str, payload: dict[str, Any]) -> str:
        """追加一个事件到任务事件流。返回 event_id。"""
        stream = k_task_event_seq(task_id)
        seq = await self.client.incr(stream)
        body = dict(payload)
        body.setdefault("event_id", f"e_{seq}")
        body["seq"] = seq
        await self.client.xadd(k_task_events_stream(task_id), {"data": json.dumps(body, ensure_ascii=False)})
        return body["event_id"]

    async def xread_events(
        self,
        task_id: str,
        last_id: str = "$",
        *,
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """从 `last_id` 起订阅任务事件流。

        - last_id 形如 `123-0`，首次订阅用 `0` 全量重放；新订阅用 `$` 仅读新事件。
        - yield (event_id, payload)
        """
        client = self.client
        stream = k_task_events_stream(task_id)
        cur_last = last_id
        while True:
            res = await client.xread({stream: cur_last}, block=block_ms, count=count)
            if not res:
                yield ("__heartbeat__", {"task_id": task_id})
                continue
            for _stream, entries in res:
                for entry_id, fields in entries:
                    cur_last = entry_id
                    raw = fields.get("data", "{}")
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = {"raw": raw}
                    yield (entry_id, payload)

    # ---- 高级 API：KV ----
    async def kv_set(self, key: str, value: Any, *, ttl: Optional[int] = None) -> None:
        v = value if isinstance(value, (str, int, float, bytes)) else json.dumps(value, ensure_ascii=False)
        await self.client.set(key, v, ex=ttl)

    async def kv_get(self, key: str) -> Any:
        v = await self.client.get(key)
        if v is None:
            return None
        try:
            return json.loads(v)
        except (TypeError, ValueError):
            return v

    # ---- 高级 API：队列 ----
    async def enqueue(self, queue: str, item: Any) -> int:
        body = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return int(await self.client.lpush(k_queue(queue), body))

    async def dequeue(self, queue: str, *, block_ms: int = 0) -> Optional[dict[str, Any]]:
        if block_ms > 0:
            res = await self.client.brpop(k_queue(queue), timeout=block_ms / 1000)
        else:
            res = await self.client.rpop(k_queue(queue))
        if not res:
            return None
        _key, raw = res
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {"raw": raw}


# ---- 全局单例 ----
_manager: Optional[RedisManager] = None


async def init_redis(url: str, max_connections: int = 32) -> RedisManager:
    global _manager
    if _manager is None:
        _manager = RedisManager(url=url, max_connections=max_connections)
        await _manager.connect()
    return _manager


def get_redis() -> RedisManager:
    if _manager is None:
        raise RuntimeError("Redis not initialized. Call init_redis() during startup.")
    return _manager


async def close_redis() -> None:
    global _manager
    if _manager is not None:
        await _manager.close()
        _manager = None
