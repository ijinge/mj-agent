"""基于 Redis Stream 的事件订阅器（XREAD 循环）。"""
from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis

_log = get_logger(__name__)


class RedisStreamSubscriber:
    """封装对 `mj:task:<id>:events` 的订阅。"""

    def __init__(self, redis: RedisManager | None = None) -> None:
        self._redis = redis or get_redis()

    async def subscribe(
        self,
        task_id: str,
        *,
        last_id: str = "$",
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """异步生成 (entry_id, payload)。

        - last_id="0"   : 全量重放（断点续传/补偿）
        - last_id="<id>": 从该 id 之后续读
        - last_id="$"   : 只读新事件
        """
        async for entry_id, payload in self._redis.xread_events(
            task_id, last_id=last_id, block_ms=block_ms, count=count
        ):
            if entry_id == "__heartbeat__":
                # 上层可以借此发送 SSE 注释行
                yield (entry_id, payload)
            else:
                yield (entry_id, payload)
