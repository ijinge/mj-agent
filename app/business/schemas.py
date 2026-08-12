"""业务层 Schema（DTO）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.task import TaskStatus


class CreateTaskDTO(BaseModel):
    user_id: str
    game_id: str = Field(..., description="地方麻将类型 ID，必须匹配 MCP server name")
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    stream: bool = True

    @field_validator("game_id")
    @classmethod
    def validate_game_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("game_id must not be empty")
        return normalized


class TaskResponseDTO(BaseModel):
    task_id: str
    user_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    last_event_seq: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
