"""FastAPI 路由：SSE 任务流、任务创建/查询/取消。"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.business.dispatcher import TaskDispatcher
from app.business.schemas import CreateTaskDTO, TaskResponseDTO
from app.business.task_service import TaskService
from app.common.async_utils import cancelable_sleep
from app.common.logger import get_logger
from app.common.redis_client import RedisManager, close_redis, get_redis, init_redis
from app.db.database import Database, close_database, get_database, init_database
from app.gateway.connection import ConnectionManager
from app.gateway.sse import sse_done, sse_format, sse_keepalive
from app.gateway.subscription import RedisStreamSubscriber
from app.models.event import Event, EventType
from app.models.task import TaskStatus
from config.settings import Settings, get_settings

_log = get_logger(__name__)


# ---- lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    await init_redis(settings.redis.url, max_connections=settings.redis.max_connections)
    await init_database(
        settings.database.url, pool_size=settings.database.pool_size, echo=settings.database.echo
    )
    yield
    await close_database()
    await close_redis()


def build_router() -> APIRouter:
    router = APIRouter()
    settings = get_settings()
    conn_mgr = ConnectionManager(max_idle_seconds=settings.gateway.sse_max_idle_seconds)
    subscriber = RedisStreamSubscriber()

    @router.post("/tasks", response_model=TaskResponseDTO, status_code=201)
    async def create_task(dto: CreateTaskDTO) -> TaskResponseDTO:
        svc = TaskService()
        dispatcher = TaskDispatcher(settings.worker.queue)
        task = await svc.create(dto)
        await dispatcher.dispatch(task)
        return await svc.to_dto(task)

    @router.get("/tasks/{task_id}", response_model=TaskResponseDTO)
    async def get_task(task_id: str) -> TaskResponseDTO:
        svc = TaskService()
        task = await svc.get(task_id)
        if not task:
            raise HTTPException(404, "task not found")
        return await svc.to_dto(task)

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict:
        ok = await TaskService().cancel(task_id)
        if not ok:
            raise HTTPException(409, "task not cancellable")
        return {"task_id": task_id, "status": TaskStatus.CANCELLED.value}

    @router.get("/tasks/{task_id}/events")
    async def stream_task_events(
        task_id: str,
        request: Request,
        last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """SSE 任务流：支持 Last-Event-ID 断点续传与 keepalive。"""
        svc = TaskService()
        task = await svc.get(task_id)
        if not task:
            raise HTTPException(404, "task not found")

        rec = await conn_mgr.register(task_id)
        start_id = last_event_id or "0"

        async def gen():
            try:
                # 启动时下发 retry 提示
                yield sse_format(
                    event_id="0-0",
                    event="open",
                    data={"task_id": task_id, "retry_ms": settings.gateway.sse_default_retry_ms},
                    retry=settings.gateway.sse_default_retry_ms,
                )
                last_id = start_id
                last_heartbeat = asyncio.get_event_loop().time()
                while True:
                    if await request.is_disconnected():
                        _log.info("client disconnected task_id=%s conn_id=%s", task_id, rec.connection_id)
                        break
                    idle = await conn_mgr.idle_seconds(rec.connection_id)
                    if idle is not None and idle > settings.gateway.sse_max_idle_seconds:
                        _log.info("sse idle timeout task_id=%s", task_id)
                        break

                    try:
                        async for entry_id, payload in subscriber.subscribe(
                            task_id, last_id=last_id, block_ms=settings.redis.stream_block_ms
                        ):
                            if entry_id == "__heartbeat__":
                                # 周期性 keepalive
                                now = asyncio.get_event_loop().time()
                                if now - last_heartbeat >= settings.gateway.sse_keepalive_seconds:
                                    yield sse_keepalive()
                                    last_heartbeat = now
                                continue
                            last_id = entry_id
                            await conn_mgr.touch(rec.connection_id)
                            ev_type = str(payload.get("type", EventType.MESSAGE.value))
                            data = {
                                "event_id": payload.get("event_id"),
                                "seq": payload.get("seq"),
                                "data": payload.get("data", {}),
                            }
                            yield sse_format(event_id=entry_id, event=ev_type, data=data)
                            if ev_type in (EventType.FINISHED.value, EventType.ERROR.value):
                                # 终止态 -> 结束流
                                yield sse_done()
                                return
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001
                        _log.exception("sse loop error task_id=%s", task_id)
                        await cancelable_sleep(0.5)
            finally:
                await conn_mgr.unregister(rec.connection_id)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router


def build_app() -> FastAPI:
    """构造 FastAPI 应用（含 lifespan）。"""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(build_router(), prefix="/api/v1")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "app": settings.app_name, "env": settings.env}

    return app


app = build_app()
