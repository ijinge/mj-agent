"""任务模型：Task 状态机与入参/出参。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务生命周期状态。"""

    PENDING = "pending"  # 已创建，待 worker 拉取
    RUNNING = "running"  # 正在执行
    STREAMING = "streaming"  # 正在产出事件
    COMPLETED = "completed"  # 正常结束
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 被取消
    TIMEOUT = "timeout"  # 超时


TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT}
)


class TaskCreateRequest(BaseModel):
    """业务层创建任务的入参。"""

    user_id: str = Field(..., description="提交用户/调用方标识")
    game_id: str = Field(..., description="地方麻将类型 ID，必须匹配 MCP server name")
    prompt: str = Field(..., description="任务输入文本")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")
    stream: bool = Field(default=True, description="是否走 SSE 流式返回")


class Task(BaseModel):
    """任务结构体（DB 持久化字段 + 运行时状态）。"""

    task_id: str
    user_id: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_event_seq: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def touch(self, status: TaskStatus | None = None, error: str | None = None) -> None:
        if status is not None:
            self.status = status
        if error is not None:
            self.error = error
        self.updated_at = datetime.utcnow()
