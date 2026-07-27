"""SSE 帧编码工具。"""
from __future__ import annotations

import json
from typing import Any, Optional


def _ensure_str(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False)


def sse_format(
    *,
    event_id: str,
    event: str,
    data: Any,
    retry: Optional[int] = None,
) -> str:
    """编码一个 SSE 帧。

    每行以 `\\n` 结尾，data 多行时按 SSE 规范每行前缀 `data: `。
    """
    lines: list[str] = []
    if retry is not None:
        lines.append(f"retry: {int(retry)}")
    if event_id:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    body = _ensure_str(data)
    for ln in body.splitlines() or [""]:
        lines.append(f"data: {ln}")
    return "\n".join(lines) + "\n\n"


def sse_keepalive(comment: str = "ka") -> str:
    """SSE 注释行（防止代理超时）。"""
    return f": {comment}\n\n"


def sse_done() -> str:
    return "event: done\ndata: {}\n\n"
