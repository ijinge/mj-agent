"""统一配置加载。

优先级：环境变量 > config/config.yaml > 代码默认
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

CONFIG_FILE = Path(__file__).parent / "config.yaml"


class RedisConfig(BaseModel):
    url: str = "redis://127.0.0.1:6379/0"
    max_connections: int = 32
    stream_block_ms: int = 5000
    stream_read_count: int = 100


class DatabaseConfig(BaseModel):
    url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/mjagent"
    pool_size: int = 10
    echo: bool = False


class GatewayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    sse_keepalive_seconds: float = 15.0
    sse_max_idle_seconds: float = 90.0
    sse_default_retry_ms: int = 3000


class WorkerConfig(BaseModel):
    queue: str = "tasks:default"
    concurrency: int = 4
    poll_block_ms: int = 1000
    event_flush_interval_ms: int = 50  # 事件聚合刷新间隔
    default_max_iters: int = 10


class LLMConfig(BaseModel):
    """LLM provider 配置（worker 实际调用时使用）。"""

    provider: str = "openai"           # openai / anthropic / ollama
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None


class MCPServerConfig(BaseModel):
    """单个 MCP server 配置。

    三种 transport 互斥：
    - stdio:            启动子进程（最常见：mcp-server-xxx）
    - sse:              远端 SSE MCP server
    - streamable_http:  远端 HTTP MCP server（新版）
    """

    name: str
    transport: str = "stdio"            # stdio | sse | streamable_http
    enabled: bool = True

    # stdio
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str | None = None

    # sse / streamable_http
    url: str | None = None
    headers: dict[str, str] = {}

    # 通用
    connect_timeout_seconds: float = 10.0
    request_timeout_seconds: float = 60.0
    tool_call_timeout_seconds: float = 120.0

    def transport_kind(self) -> str:
        return self.transport.lower().strip()


class MCPConfig(BaseModel):
    """MCP 总配置。"""

    enabled: bool = True
    servers: list[MCPServerConfig] = []
    # 工具白/黑名单（按 server:name 限定），不填表示全量
    allowlist: list[str] = []
    denylist: list[str] = []
    # 工具调用时是否把 call / result 写回事件流
    emit_tool_events: bool = True


class Settings(BaseModel):
    app_name: str = "mj-agent"
    env: str = "dev"
    redis: RedisConfig = Field(default_factory=RedisConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


def _load_yaml() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config file: {CONFIG_FILE}")
    return data


def _apply_env_overrides(settings: Settings) -> Settings:
    """环境变量覆盖常见字段。"""
    env_map: dict[str, tuple[str, ...]] = {
        "MJ_REDIS_URL": ("redis", "url"),
        "MJ_DB_URL": ("database", "url"),
        "MJ_GATEWAY_HOST": ("gateway", "host"),
        "MJ_GATEWAY_PORT": ("gateway", "port"),
        "MJ_WORKER_CONCURRENCY": ("worker", "concurrency"),
        "MJ_LLM_PROVIDER": ("llm", "provider"),
        "MJ_LLM_MODEL": ("llm", "model"),
        "MJ_LLM_API_KEY": ("llm", "api_key"),
        "MJ_LLM_BASE_URL": ("llm", "base_url"),
        "MJ_ENV": ("env",),
    }
    for env_key, path in env_map.items():
        v = os.getenv(env_key)
        if v is None:
            continue
        target = settings
        for p in path[:-1]:
            target = getattr(target, p)  # type: ignore[assignment]
        attr = path[-1]
        # 类型转换
        cur = getattr(target, attr)
        if isinstance(cur, bool):
            cast: Any = v.lower() in {"1", "true", "yes", "on"}
        elif isinstance(cur, int):
            cast = int(v)
        elif isinstance(cur, float):
            cast = float(v)
        else:
            cast = v
        setattr(target, attr, cast)
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw = _load_yaml()
    settings = Settings.model_validate(raw) if raw else Settings()
    return _apply_env_overrides(settings)


def reload_settings() -> Settings:
    """测试时用于刷新缓存。"""
    get_settings.cache_clear()
    return get_settings()
