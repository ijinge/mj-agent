"""事件聚合测试。"""
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
from app.models.event import Event, EventType
from app.worker.event_aggregator import EventAggregator


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


def _mkev(task_id: str, text: str) -> Event:
    return Event(
        event_id="",
        task_id=task_id,
        type=EventType.TOKEN,
        data={"text": text},
        seq=0,
        created_at_ms=0,
    )


async def test_aggregator_batches_tokens(fake_redis: RedisManager):
    task_id = "t_agg_batch"
    agg = EventAggregator(max_batch=4, flush_interval_ms=20, redis=fake_redis)
    await agg.start()
    try:
        for s in ["h", "e", "l", "l", "o"]:
            await agg.enqueue(_mkev(task_id, s))
        # 触发 max_batch flush
        await asyncio.sleep(0.05)
        # 等聚合器周期 flush
        await agg.flush_all()
        # 至少应该有 1 条（合并后），且不超过 2 条
        entries = await fake_redis.client.xrange(f"mj:task:{task_id}:events")
        assert 1 <= len(entries) <= 2
        texts: list[str] = []
        for _eid, fields in entries:
            data = json.loads(fields["data"])
            if data.get("type") == EventType.TOKEN.value:
                texts.append(data.get("data", {}).get("text", ""))
        assert "".join(["h", "e", "l", "l", "o"]) in "".join(texts)
    finally:
        await agg.stop()


async def test_aggregator_preserves_order(fake_redis: RedisManager):
    task_id = "t_agg_order"
    agg = EventAggregator(max_batch=2, flush_interval_ms=10, redis=fake_redis)
    await agg.start()
    try:
        for s in ["a", "b", "c", "d"]:
            await agg.enqueue(_mkev(task_id, s))
        await agg.flush_all()
        entries = await fake_redis.client.xrange(f"mj:task:{task_id}:events")
        seqs: list[int] = []
        for _eid, fields in entries:
            data = json.loads(fields["data"])
            if "seq" in data:
                seqs.append(int(data["seq"]))
        assert seqs == sorted(seqs)
        assert seqs[0] == 1 and seqs[-1] == 4
    finally:
        await agg.stop()


async def test_non_aggregable_event_flushes_immediately(fake_redis: RedisManager):
    task_id = "t_agg_msg"
    agg = EventAggregator(max_batch=100, flush_interval_ms=10_000, redis=fake_redis)
    try:
        msg = Event(
            event_id="",
            task_id=task_id,
            type=EventType.MESSAGE,
            data={"text": "hello"},
            seq=0,
            created_at_ms=0,
        )
        await agg.enqueue(msg)
        # 非聚合事件应立即写入，不需 flush
        entries = await fake_redis.client.xrange(f"mj:task:{task_id}:events")
        assert len(entries) == 1
        data = json.loads(entries[0][1]["data"])
        assert data["type"] == EventType.MESSAGE.value
    finally:
        await agg.stop()
