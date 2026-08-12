"""地方麻将类型 ID 到 MCP server 的路由隔离测试。"""

from __future__ import annotations

import pytest

from app.business.schemas import CreateTaskDTO
from app.worker.mcp.registry import ToolDescriptor, ToolRegistry
from app.worker.runner import WorkerRunner, _get_explicit_game_id


def _runner_with_servers() -> WorkerRunner:
    runner = WorkerRunner.__new__(WorkerRunner)
    runner._mcp = object()  # type: ignore[attr-defined]
    runner._tool_registry = ToolRegistry()  # type: ignore[attr-defined]
    runner._tool_registry.register(  # type: ignore[attr-defined]
        ToolDescriptor("ncmj-server", "decision", "ncmj-server:decision", "", {})
    )
    runner._tool_registry.register(  # type: ignore[attr-defined]
        ToolDescriptor("srmj-server", "decision", "srmj-server:decision", "", {})
    )
    runner._graphs_by_server = {}  # type: ignore[attr-defined]
    runner._build_graph = lambda server_name=None: f"graph:{server_name}"  # type: ignore[method-assign]
    return runner


def test_create_task_requires_and_normalizes_game_id() -> None:
    dto = CreateTaskDTO(user_id="u", game_id="  ncmj-server  ", prompt="question")
    assert dto.game_id == "ncmj-server"

    with pytest.raises(ValueError, match="game_id"):
        CreateTaskDTO(user_id="u", game_id="   ", prompt="question")


def test_graph_routes_by_exact_mcp_server_name_and_caches() -> None:
    runner = _runner_with_servers()
    first = runner._graph_for_game_id("ncmj-server")
    second = runner._graph_for_game_id(" ncmj-server ")

    assert first == "graph:ncmj-server"
    assert second is first
    assert list(runner._graphs_by_server) == ["ncmj-server"]  # type: ignore[attr-defined]


def test_graph_rejects_unknown_game_id_without_falling_back_to_all_tools() -> None:
    runner = _runner_with_servers()

    with pytest.raises(ValueError, match="available: ncmj-server, srmj-server"):
        runner._graph_for_game_id("unknown-server")


def test_game_state_is_never_used_as_game_id() -> None:
    """牌局 JSON 即使包含 game_id，也不能参与 MCP server 路由。"""
    item = {
        "game_id": "ncmj-server",
        "metadata": {
            "game_state": {"game_id": "srmj-server"},
        },
    }
    explicit_game_id = _get_explicit_game_id(item)
    assert explicit_game_id == "ncmj-server"
    assert _get_explicit_game_id({"metadata": item["metadata"]}) == ""
