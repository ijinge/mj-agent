"""业务层 Schema（DTO）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.task import TaskStatus


class CreateTaskDTO(BaseModel):
    user_id: str
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    stream: bool = True


class TaskResponseDTO(BaseModel):
    task_id: str
    user_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    last_event_seq: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
