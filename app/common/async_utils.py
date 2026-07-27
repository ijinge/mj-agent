"""asyncio 工具集。

- gather_with_concurrency: 限制并发上限
- cancelable_sleep:        可取消的 sleep（用于心跳/退避）
- fire_and_forget:         后台任务托管（带异常回调）
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Iterable, TypeVar

from app.common.logger import get_logger

_log = get_logger(__name__)

T = TypeVar("T")


async def gather_with_concurrency(
    limit: int, coros: Iterable[Awaitable[T]]
) -> list[T]:
    """限制最大并发的 gather。"""
    sem = asyncio.Semaphore(limit)
    results: list[T] = []

    async def _wrap(c: Awaitable[T]) -> T:
        async with sem:
            return await c

    return await asyncio.gather(*(_wrap(c) for c in coros))


async def cancelable_sleep(seconds: float) -> None:
    """可取消的 sleep。"""
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        raise


def fire_and_forget(
    coro: Awaitable[Any],
    *,
    name: str | None = None,
    on_error: Callable[[BaseException], None] | None = None,
) -> asyncio.Task[Any]:
    """将协程放入后台执行并记录异常。"""
    task = asyncio.create_task(coro, name=name)
    def _done_callback(t: asyncio.Task[Any]) -> None:
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except BaseException as exc:  # noqa: BLE001
            if on_error is not None:
                try:
                    on_error(exc)
                except Exception:  # noqa: BLE001
                    _log.exception("on_error callback raised")
            _log.exception("background task %s failed", t.get_name())
    task.add_done_callback(_done_callback)
    return task
