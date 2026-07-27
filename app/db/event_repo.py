"""事件持久化（Event Repository）。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, JSON, select, and_
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base, Database, get_database
from app.models.event import Event, EventType


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    @classmethod
    def from_model(cls, e: Event) -> "EventRow":
        return cls(
            task_id=e.task_id,
            event_id=e.event_id,
            seq=e.seq,
            type=e.type.value,
            data=e.data,
            created_at=datetime.utcnow(),
        )

    def to_model(self) -> Event:
        return Event(
            event_id=self.event_id,
            task_id=self.task_id,
            type=EventType(self.type),
            data=self.data or {},
            seq=self.seq,
            created_at_ms=int(self.created_at.timestamp() * 1000) if self.created_at else 0,
        )


class EventRepository:
    def __init__(self, db: Database | None = None) -> None:
        self._db = db or get_database()

    async def append(self, event: Event) -> None:
        async with self._db.session() as s:
            s.add(EventRow.from_model(event))
            await s.commit()

    async def list_after_seq(
        self, task_id: str, after_seq: int = 0, limit: int = 200
    ) -> list[Event]:
        """按序号续读事件（断点续传/补偿）。"""
        async with self._db.session() as s:
            stmt = (
                select(EventRow)
                .where(and_(EventRow.task_id == task_id, EventRow.seq > after_seq))
                .order_by(EventRow.seq.asc())
                .limit(limit)
            )
            res = await s.execute(stmt)
            return [r.to_model() for r in res.scalars().all()]

    async def get(self, event_id: str) -> Optional[Event]:
        async with self._db.session() as s:
            stmt = select(EventRow).where(EventRow.event_id == event_id)
            res = await s.execute(stmt)
            r = res.scalar_one_or_none()
            return r.to_model() if r else None
