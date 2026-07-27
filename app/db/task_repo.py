"""任务状态持久化（Task Repository）。

使用 SQLAlchemy 2.x 异步 ORM。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, JSON, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base, Database, get_database
from app.models.task import Task, TaskStatus


class TaskRow(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    prompt: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.PENDING.value, index=True)
    task_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    last_event_seq: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @classmethod
    def from_model(cls, t: Task) -> "TaskRow":
        return cls(
            task_id=t.task_id,
            user_id=t.user_id,
            prompt=t.prompt,
            status=t.status.value,
            task_metadata=t.metadata,
            last_event_seq=t.last_event_seq,
            error=t.error,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )

    def to_model(self) -> Task:
        return Task(
            task_id=self.task_id,
            user_id=self.user_id,
            prompt=self.prompt,
            status=TaskStatus(self.status),
            metadata=self.task_metadata or {},
            last_event_seq=self.last_event_seq,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class TaskRepository:
    def __init__(self, db: Database | None = None) -> None:
        self._db = db or get_database()

    async def upsert(self, task: Task) -> None:
        async with self._db.session() as s:
            row = TaskRow.from_model(task)
            await s.merge(row)
            await s.commit()

    async def get(self, task_id: str) -> Optional[Task]:
        async with self._db.session() as s:
            r = await s.get(TaskRow, task_id)
            return r.to_model() if r else None

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        error: Optional[str] = None,
    ) -> None:
        async with self._db.session() as s:
            r = await s.get(TaskRow, task_id)
            if not r:
                return
            r.status = status.value
            if error is not None:
                r.error = error
            r.updated_at = datetime.utcnow()
            await s.commit()

    async def set_last_seq(self, task_id: str, seq: int) -> None:
        async with self._db.session() as s:
            r = await s.get(TaskRow, task_id)
            if not r:
                return
            if seq > r.last_event_seq:
                r.last_event_seq = seq
                await s.commit()

    async def list_by_user(self, user_id: str, limit: int = 50) -> list[Task]:
        async with self._db.session() as s:
            stmt = (
                select(TaskRow)
                .where(TaskRow.user_id == user_id)
                .order_by(TaskRow.created_at.desc())
                .limit(limit)
            )
            res = await s.execute(stmt)
            return [r.to_model() for r in res.scalars().all()]
