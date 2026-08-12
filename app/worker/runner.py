"""Worker Runner：消费队列、初始化 MCP 客户端、调度 agent loop、产出事件。"""

from __future__ import annotations

import asyncio
import signal
import time
from typing import Any

from app.business.dispatcher import TaskDispatcher
from app.common.async_utils import cancelable_sleep, fire_and_forget
from app.common.logger import get_logger
from app.common.redis_client import RedisManager, close_redis, get_redis, init_redis
from app.db.database import close_database, init_database
from app.db.task_repo import TaskRepository
from app.models.event import Event, EventType
from app.models.task import TaskStatus
from app.worker.agent import build_default_graph, create_llm, run_agent
from app.worker.event_aggregator import EventAggregator
from app.worker.mcp import MCPClientManager, ToolRegistry, build_tool_node, mcp_to_langchain_tools
from app.worker.state import StateManager
from config.settings import Settings, get_settings

_log = get_logger(__name__)


def _get_explicit_game_id(item: dict[str, Any]) -> str:
    """只读取前端请求进入队列顶层后的 game_id，不检查 game_state。"""
    return str(item.get("game_id") or "").strip()


class WorkerRunner:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        redis: RedisManager | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._redis = redis or get_redis()
        self._dispatcher = TaskDispatcher(self._settings.worker.queue, redis=self._redis)
        self._repo = TaskRepository()
        self._aggregator = EventAggregator(
            max_batch=16,
            flush_interval_ms=self._settings.worker.event_flush_interval_ms,
            redis=self._redis,
        )
        self._state = StateManager(redis=self._redis)
        self._mcp: MCPClientManager | None = None
        self._tool_registry = ToolRegistry(self._settings.mcp)
        self._graph = None  # CompiledStateGraph | None
        self._graphs_by_server: dict[str, Any] = {}
        self._stop_evt = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()

    # ---- lifecycle ----
    async def start(self) -> None:
        # 1. 启动事件聚合器
        await self._aggregator.start()

        # 2. 启动 MCP（可选）
        await self._start_mcp()

        # 3. 构造 agent graph（带 MCP 工具）
        self._graph = self._build_graph()

        # 4. 启动 worker 协程
        for i in range(self._settings.worker.concurrency):
            t = asyncio.create_task(self._worker_loop(i), name=f"worker-{i}")
            self._tasks.add(t)
        _log.info(
            "worker started concurrency=%s mcp_servers=%s tools=%s",
            self._settings.worker.concurrency,
            self._mcp.server_names() if self._mcp else [],
            len(self._tool_registry),
        )

    async def stop(self) -> None:
        self._stop_evt.set()
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._aggregator.stop()
        if self._mcp is not None:
            await self._mcp.aclose()
            self._mcp = None
        self._graphs_by_server.clear()
        _log.info("worker stopped")

    # ---- internals ----
    async def _start_mcp(self) -> None:
        mcp_cfg = self._settings.mcp
        if not mcp_cfg.enabled or not mcp_cfg.servers:
            _log.info("MCP disabled or no servers configured")
            return
        mgr = MCPClientManager(mcp_cfg.servers)
        try:
            await mgr.connect()
        except Exception:  # noqa: BLE001
            _log.exception("MCP connect failed; running without MCP tools")
            await mgr.aclose()
            return
        self._mcp = mgr
        # 加载工具到 registry
        try:
            all_tools = await mgr.list_all_tools()
            for server_name, tools in all_tools.items():
                self._tool_registry.register_many(server_name, tools)
            _log.info("MCP tools loaded count=%s", len(self._tool_registry))
        except Exception:  # noqa: BLE001
            _log.exception("MCP list_all_tools failed")

    def _build_graph(self, server_name: str | None = None):
        """构造仅绑定指定 MCP server 工具的 graph；未指定时不绑定工具。"""
        # 没有 LLM 配置时不调真实 LLM（用占位 chat）
        if not (self._settings.llm.api_key or self._settings.llm.provider in {"ollama"}):
            _log.warning("no LLM api_key configured; using placeholder chat node")
            return build_default_graph()

        try:
            llm = create_llm(self._settings.llm)
        except Exception:  # noqa: BLE001
            _log.exception("create_llm failed; using placeholder")
            return build_default_graph()

        # 桥接 MCP 工具
        tools: list[Any] = []
        if server_name and self._mcp is not None and len(self._tool_registry) > 0:
            try:
                tools = mcp_to_langchain_tools(
                    self._mcp,
                    self._tool_registry,
                    server_name=server_name,
                )
                if not tools:
                    raise ValueError(f"MCP server '{server_name}' has no available tools")
                # 包装 ToolNode 写 TOOL_CALL / TOOL_RESULT 事件
                if self._settings.mcp.emit_tool_events:
                    tool_node = build_tool_node(
                        tools,
                        aggregator=self._aggregator,
                    )
                    return build_default_graph(llm=llm, tools=tools, tool_node=tool_node)
            except Exception:  # noqa: BLE001
                _log.exception("MCP bridge failed server_name=%s", server_name)
                raise

        return build_default_graph(llm=llm, tools=tools)

    def _graph_for_game_id(self, game_id: str):
        """按地方麻将类型 ID 路由到同名 MCP server，并缓存隔离后的 graph。"""
        server_name = game_id.strip()
        if not server_name:
            raise ValueError("game_id is required")
        if self._mcp is None:
            raise RuntimeError("MCP is unavailable; cannot route game_id")

        descriptors = self._tool_registry.by_server(server_name)
        if not descriptors:
            available = sorted({item.server_name for item in self._tool_registry.all()})
            choices = ", ".join(available) if available else "none"
            raise ValueError(
                f"game_id '{server_name}' does not match an MCP server; available: {choices}"
            )

        graph = self._graphs_by_server.get(server_name)
        if graph is None:
            graph = self._build_graph(server_name)
            self._graphs_by_server[server_name] = graph
            _log.info(
                "agent graph routed game_id=%s tool_count=%s",
                server_name,
                len(descriptors),
            )
        return graph

    async def _worker_loop(self, idx: int) -> None:
        while not self._stop_evt.is_set():
            try:
                item = await self._dispatcher.fetch(block_ms=self._settings.worker.poll_block_ms)
                if not item:
                    continue
                await self._process(item)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                _log.exception("worker[%s] loop error", idx)
                await cancelable_sleep(0.5)

    async def _process(self, item: dict[str, Any]) -> None:
        task_id = item.get("task_id", "")
        if not task_id:
            _log.warning("invalid task item: %s", item)
            return
        _log.info("worker processing task_id=%s", task_id)
        await self._repo.update_status(task_id, TaskStatus.RUNNING)
        try:
            coro = self._run_agent_for_task(task_id, item)
            fire_and_forget(coro, name=f"run-agent-{task_id}")
        except Exception:  # noqa: BLE001
            _log.exception("dispatch agent failed task_id=%s", task_id)
            await self._repo.update_status(task_id, TaskStatus.FAILED, error="dispatch_failed")

    async def _run_agent_for_task(self, task_id: str, item: dict[str, Any]) -> None:
        metadata = item.get("metadata") or {}
        # 路由 ID 只能来自前端显式提交并进入队列顶层的 game_id。
        # 不从 game_state 或其他 metadata 字段推断，避免把牌局内容当作玩法路由。
        game_id = _get_explicit_game_id(item)
        try:
            graph = self._graph_for_game_id(game_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "task routing failed task_id=%s game_id=%s error=%s", task_id, game_id, exc
            )
            await self._aggregator.enqueue(
                Event(
                    event_id="",
                    task_id=task_id,
                    type=EventType.ERROR,
                    data={"message": str(exc), "game_id": game_id},
                    seq=0,
                    created_at_ms=int(time.time() * 1000),
                )
            )
            await self._repo.update_status(task_id, TaskStatus.FAILED, error=str(exc))
            return

        try:
            await self._repo.update_status(task_id, TaskStatus.STREAMING)
            # 从 task metadata 提取 game_state，供 tool_node 替换占位符
            game_state = metadata.get("game_state")
            if game_state is None:
                _log.debug("task_id=%s has no game_state in metadata", task_id)
            async for _ in run_agent(
                task_id=task_id,
                prompt=item.get("prompt", ""),
                aggregator=self._aggregator,
                state_manager=self._state,
                graph=graph,
                max_iters=self._settings.worker.default_max_iters,
                game_id=game_id,
                game_state=game_state,
            ):
                pass
            await self._aggregator.flush_all()
            await self._repo.update_status(task_id, TaskStatus.COMPLETED)
        except Exception as exc:  # noqa: BLE001
            _log.exception("agent run failed task_id=%s", task_id)
            await self._repo.update_status(task_id, TaskStatus.FAILED, error=str(exc))


async def main() -> None:
    settings = get_settings()
    await init_redis(settings.redis.url, max_connections=settings.redis.max_connections)
    await init_database(
        settings.database.url,
        pool_size=settings.database.pool_size,
        echo=settings.database.echo,
    )

    # 2) 构造 runner（此时 get_redis / get_database 都能拿到全局单例）
    runner = WorkerRunner()
    await runner.start()

    loop = asyncio.get_event_loop()

    def _shutdown() -> None:
        _log.info("shutdown signal received")
        loop.create_task(runner.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    try:
        await runner._stop_evt.wait()
    finally:
        await runner.stop()
        await close_database()
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
