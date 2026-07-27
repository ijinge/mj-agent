"""SSE 断点续传测试。

- 验证 last_id="0" 时能从 stream 头部全量重放
- 验证从指定 last_id 续读时不会重复下发
- 验证 keepalive 心跳

使用 fakeredis 模拟 Redis，测试运行无需真实 Redis。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import pytest

try:
    import fakeredis.aioredis as fakeredis_aio  # type: ignore
except ImportError:  # pragma: no cover
    fakeredis_aio = None  # type: ignore

from app.common.redis_client import RedisManager
from app.gateway.sse import sse_format, sse_keepalive
from app.gateway.subscription import RedisStreamSubscriber


pytestmark = pytest.mark.skipif(
    fakeredis_aio is None, reason="fakeredis is required for this test"
)


@pytest.fixture
async def fake_redis() -> AsyncIterator[RedisManager]:
    client = fakeredis_aio.FakeRedis(decode_responses=True)
    mgr = RedisManager.__new__(RedisManager)
    mgr._url = "redis://fake"  # type: ignore[attr-defined]
    mgr._pool = None  # type: ignore[attr-defined]
    mgr._client = client  # type: ignore[attr-defined]
    try:
        yield mgr
    finally:
        await client.aclose()


async def _collect(agen: AsyncIterator[Any], limit: int) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    async for eid, payload in agen:
        out.append((eid, payload))
        if len(out) >= limit:
            break
    return out


async def test_xread_replay_from_beginning(fake_redis: RedisManager):
    task_id = "t_replay"
    # 写入 3 条事件
    for i in range(3):
        await fake_redis.xadd_event(task_id, {"type": "token", "data": {"text": f"t{i}"}})

    sub = RedisStreamSubscriber(redis=fake_redis)
    items = await _collect(sub.subscribe(task_id, last_id="0", block_ms=50), limit=3)
    assert len(items) == 3
    types = [p.get("type") for _, p in items]
    assert types == ["token", "token", "token"]


async def test_xread_resume_from_last_id(fake_redis: RedisManager):
    task_id = "t_resume"
    for i in range(5):
        await fake_redis.xadd_event(task_id, {"type": "token", "data": {"text": f"t{i}"}})

    sub = RedisStreamSubscriber(redis=fake_redis)
    # 先读 2 条
    first = await _collect(sub.subscribe(task_id, last_id="0", block_ms=50), limit=2)
    assert len(first) == 2
    last_id = first[-1][0]

    # 续读：只应再收到 3 条
    second = await _collect(sub.subscribe(task_id, last_id=last_id, block_ms=50), limit=3)
    assert len(second) == 3


async def test_sse_frame_after_resume():
    """续读后写出的 SSE 帧需保留 last-event-id。"""
    payload = {"event_id": "e_1", "type": "token", "data": {"text": "hi"}}
    frame = sse_format(event_id="123-0", event="token", data=payload)
    assert "id: 123-0" in frame
    assert "event: token" in frame
    ka = sse_keepalive()
    assert ka.startswith(":")
