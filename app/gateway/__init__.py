"""gateway: SSE 网关（StreamingResponse、断线重连、XREAD 订阅）。"""

from app.gateway.sse import sse_format, sse_done, sse_keepalive
from app.gateway.connection import ConnectionManager
from app.gateway.subscription import RedisStreamSubscriber

__all__ = [
    "sse_format",
    "sse_done",
    "sse_keepalive",
    "ConnectionManager",
    "RedisStreamSubscriber",
    "build_router",
]


def __getattr__(name: str):
    """延迟 import build_router（避免 import 期触发 Redis 单例检查）。"""
    if name == "build_router":
        from app.gateway.router import build_router as _build_router
        return _build_router
    raise AttributeError(name)
