"""任务服务：业务侧创建、查询、取消。"""

from __future__ import annotations

from app.business.schemas import CreateTaskDTO, TaskResponseDTO
from app.common.ids import new_task_id
from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis
from app.db.task_repo import TaskRepository
from app.models.task import Task, TaskStatus

_log = get_logger(__name__)


class TaskService:
    def __init__(
        self,
        repo: TaskRepository | None = None,
        redis: RedisManager | None = None,
    ) -> None:
        self._repo = repo or TaskRepository()
        self._redis = redis or get_redis()

    async def create(self, dto: CreateTaskDTO) -> Task:
        metadata = {**dto.metadata, "game_id": dto.game_id}
        task = Task(
            task_id=new_task_id(),
            user_id=dto.user_id,
            prompt=dto.prompt,
            metadata=metadata,
        )
        await self._repo.upsert(task)
        _log.info("task created task_id=%s user_id=%s", task.task_id, task.user_id)
        return task

    async def get(self, task_id: str) -> Task | None:
        return await self._repo.get(task_id)

    async def cancel(self, task_id: str) -> bool:
        task = await self._repo.get(task_id)
        if not task:
            return False
        if task.is_terminal():
            return False
        task.touch(status=TaskStatus.CANCELLED)
        await self._repo.upsert(task)
        # 通知 worker（取消标记）
        await self._redis.kv_set(f"mj:task:{task_id}:cancel", "1", ttl=60)
        _log.info("task cancelled task_id=%s", task_id)
        return True

    async def to_dto(self, task: Task) -> TaskResponseDTO:
        return TaskResponseDTO(
            task_id=task.task_id,
            user_id=task.user_id,
            status=task.status,
            created_at=task.created_at,
            updated_at=task.updated_at,
            error=task.error,
            last_event_seq=task.last_event_seq,
            metadata=task.metadata,
        )
