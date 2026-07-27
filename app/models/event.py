"""事件模型：Worker 产出 + 网关下发。"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """事件类型。"""

    STARTED = "started"             # 任务开始
    TOKEN = "token"                 # 流式 token
    MESSAGE = "message"             # 完整消息
    TOOL_CALL = "tool_call"         # 工具调用请求
    TOOL_RESULT = "tool_result"     # 工具调用结果
    THINKING = "thinking"           # 思考过程
    PROGRESS = "progress"           # 进度更新
    ERROR = "error"                 # 错误
    FINISHED = "finished"           # 任务结束（成功）


class Event(BaseModel):
    """业务事件（worker 产出）。"""

    event_id: str
    task_id: str
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)
    seq: int = 0
    created_at_ms: int = 0


class EventEnvelope(BaseModel):
    """网关下发事件（与 SSE `id:` 对齐，用于断点续传）。"""

    id: str = Field(..., description="SSE event id，可作为 last-event-id 续读")
    event: str = Field(..., description="SSE event 名称")
    data: str = Field(..., description="SSE data 行（JSON 字符串）")
    retry: Optional[int] = Field(default=None, description="SSE retry 建议毫秒数")
