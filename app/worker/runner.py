"""Worker Runner：消费队列、调度 agent loop、产出事件。"""
from __future__ import annotations

import asyncio
import signal
from typing import Any, Optional

from app.business.dispatcher import TaskDispatcher
from app.common.async_utils import cancelable_sleep, fire_and_forget
from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis
from app.config.settings import Settings, get_settings
from app.db.task_repo import TaskRepository
from app.models.task import TaskStatus
from app.worker.agent import run_agent
from app.worker.event_aggregator import EventAggregator
from app.worker.state import StateManager

_log = get_logger(__name__)


class WorkerRunner:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        redis: RedisManager | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._redis = redis or get_redis()
        self._dispatcher = TaskDispatcher(self._settings.worker.queue, redis=self._redis)
        self._repo = TaskRepository()
        self._aggregator = EventAggregator(
            max_batch=16,
            flush_interval_ms=self._settings.worker.event_flush_interval_ms,
            redis=self._redis,
        )
        self._state = StateManager(redis=self._redis)
        self._stop_evt = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()

    async def start(self) -> None:
        await self._aggregator.start()
        for i in range(self._settings.worker.concurrency):
            t = asyncio.create_task(self._worker_loop(i), name=f"worker-{i}")
            self._tasks.add(t)
        _log.info("worker started concurrency=%s", self._settings.worker.concurrency)

    async def stop(self) -> None:
        self._stop_evt.set()
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._aggregator.stop()
        _log.info("worker stopped")

    async def _worker_loop(self, idx: int) -> None:
        while not self._stop_evt.is_set():
            try:
                item = await self._dispatcher.fetch(block_ms=self._settings.worker.poll_block_ms)
                if not item:
                    continue
                await self._process(item)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                _log.exception("worker[%s] loop error", idx)
                await cancelable_sleep(0.5)

    async def _process(self, item: dict[str, Any]) -> None:
        task_id = item.get("task_id", "")
        if not task_id:
            _log.warning("invalid task item: %s", item)
            return
        _log.info("worker processing task_id=%s", task_id)
        await self._repo.update_status(task_id, TaskStatus.RUNNING)
        try:
            # 异步跑 agent（不阻塞 worker 主循环）
            coro = self._run_agent_for_task(task_id, item)
            fire_and_forget(coro, name=f"run-agent-{task_id}")
        except Exception:  # noqa: BLE001
            _log.exception("dispatch agent failed task_id=%s", task_id)
            await self._repo.update_status(task_id, TaskStatus.FAILED, error="dispatch_failed")

    async def _run_agent_for_task(self, task_id: str, item: dict[str, Any]) -> None:
        try:
            await self._repo.update_status(task_id, TaskStatus.STREAMING)
            async for _ in run_agent(
                task_id=task_id,
                prompt=item.get("prompt", ""),
                aggregator=self._aggregator,
                state_manager=self._state,
                max_iters=self._settings.worker.default_max_iters,
            ):
                pass
            await self._aggregator.flush_all()
            await self._repo.update_status(task_id, TaskStatus.COMPLETED)
        except Exception as exc:  # noqa: BLE001
            _log.exception("agent run failed task_id=%s", task_id)
            await self._repo.update_status(task_id, TaskStatus.FAILED, error=str(exc))


async def main() -> None:
    """本地启动入口（python -m app.worker.runner）。"""
    runner = WorkerRunner()
    await runner.start()

    loop = asyncio.get_event_loop()
    def _shutdown() -> None:
        _log.info("shutdown signal received")
        loop.create_task(runner.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            # Windows: signal handlers not supported
            pass

    try:
        await runner._stop_evt.wait()
    finally:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
