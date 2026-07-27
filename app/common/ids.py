"""ID 生成器。

- task_id: 任务唯一标识（带前缀 t_）
- event_id: 事件唯一标识（带前缀 e_，单任务内单调递增，由 Redis INCR 兜底）
- connection_id: SSE 连接唯一标识（带前缀 c_）
"""
from __future__ import annotations

import secrets
import time
import uuid

_PREFIX_TASK = "t_"
_PREFIX_EVENT = "e_"
_PREFIX_CONN = "c_"


def _short_hex(n: int = 6) -> str:
    return secrets.token_hex(n)


def new_task_id() -> str:
    """生成 task_id：毫秒时间戳 + 6 字节随机。"""
    return f"{_PREFIX_TASK}{int(time.time() * 1000):x}{_short_hex(4)}"


def new_event_id(seq: int | None = None) -> str:
    """生成 event_id。

    若传入 seq，则采用 `<prefix><seq>` 形式，便于按序号排序与 SSE last-event-id 续读。
    """
    if seq is not None:
        return f"{_PREFIX_EVENT}{seq}"
    return f"{_PREFIX_EVENT}{uuid.uuid4().hex[:12]}"


def new_connection_id() -> str:
    return f"{_PREFIX_CONN}{uuid.uuid4().hex}"
