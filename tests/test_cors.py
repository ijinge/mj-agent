"""锁住 CORS middleware 配置：保证前端跨域请求的 preflight 不被 405。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """构造一个 gateway TestClient，避免 lifespan 触发真实 Redis/DB。"""
    # 关掉 lifespan，只测 CORS middleware + 路由定义
    from app.gateway import router as gw_router

    def _build():
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        from config.settings import get_settings, reload_settings

        reload_settings()
        settings = get_settings()
        app = FastAPI(title="test")
        app.state.settings = settings
        cors_kwargs = {
            "allow_origins": settings.gateway.cors_allow_origins,
            "allow_methods": settings.gateway.cors_allow_methods,
            "allow_headers": settings.gateway.cors_allow_headers,
            "allow_credentials": settings.gateway.cors_allow_credentials,
            "expose_headers": ["Last-Event-ID", "Content-Type"],
        }
        if "*" in settings.gateway.cors_allow_origins:
            cors_kwargs["allow_credentials"] = False
        app.add_middleware(CORSMiddleware, **cors_kwargs)

        @app.post("/api/v1/tasks")
        async def create_task_stub():
            return {"ok": True}

        @app.get("/healthz")
        async def healthz_stub():
            return {"ok": True}

        return app

    # 屏蔽 lifespan（TestClient 默认会跑）
    return TestClient(_build(), raise_server_exceptions=True)


def test_cors_preflight_returns_200_not_405(client) -> None:
    """浏览器跨域 POST 前会先发 OPTIONS preflight，必须返回 200。"""
    resp = client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200, f"preflight 失败 status={resp.status_code}"
    # 必须有这些 CORS 回包头
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "POST" in (resp.headers.get("access-control-allow-methods") or "").upper()


def test_cors_preflight_allows_127_origin(client) -> None:
    resp = client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


def test_cors_preflight_rejects_unknown_origin(client) -> None:
    """未在白名单的 origin 不应拿到 allow-origin 回包。"""
    resp = client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # 浏览器策略：没有 allow-origin 头就不会放行实际请求
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_cors_exposes_last_event_id_header(client) -> None:
    """SSE 断点续传依赖 Last-Event-ID，必须暴露给前端 JS。
    注意：expose_headers 只在实际请求的响应里回（不在 preflight OPTIONS 里）。
    """
    resp = client.get(
        "/healthz",
        headers={"Origin": "http://localhost:3000"},
    )
    exposed = resp.headers.get("access-control-expose-headers") or ""
    assert "Last-Event-ID" in exposed, (
        f"必须暴露 Last-Event-ID 给前端 EventSource，当前 expose_headers={exposed!r}"
    )


def test_gateway_config_has_cors_defaults() -> None:
    """锁住 GatewayConfig.cors_allow_origins 默认值（防止改回空）。"""
    from config.settings import GatewayConfig, reload_settings

    cfg = GatewayConfig()
    assert "http://localhost:3000" in cfg.cors_allow_origins, (
        "GatewayConfig.cors_allow_origins 必须默认放行 localhost:3000"
    )
    assert "http://127.0.0.1:3000" in cfg.cors_allow_origins
    # 实际配置（yaml）也必须非空
    settings = reload_settings()
    assert len(settings.gateway.cors_allow_origins) > 0
