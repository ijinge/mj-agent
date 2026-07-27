"""Worker Runner：消费队列、初始化 MCP 客户端、调度 agent loop、产出事件。"""
from __future__ import annotations

import asyncio
import signal
from typing import Any, Optional

from app.business.dispatcher import TaskDispatcher
from app.common.async_utils import cancelable_sleep, fire_and_forget
from app.common.logger import get_logger
from app.common.redis_client import RedisManager, get_redis
from app.db.task_repo import TaskRepository
from app.models.task import TaskStatus
from app.worker.agent import build_default_graph, create_llm, run_agent
from app.worker.event_aggregator import EventAggregator
from app.worker.mcp import MCPClientManager, ToolRegistry, build_tool_node, mcp_to_langchain_tools
from app.worker.state import StateManager
from config.settings import Settings, get_settings

_log = get_logger(__name__)


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
        self._mcp: Optional[MCPClientManager] = None
        self._tool_registry = ToolRegistry(self._settings.mcp)
        self._graph = None  # CompiledStateGraph | None
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

    def _build_graph(self):
        """按是否配置 LLM + MCP tools 构造 graph。"""
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
        if self._mcp is not None and len(self._tool_registry) > 0:
            try:
                tools = mcp_to_langchain_tools(self._mcp, self._tool_registry)
                # 包装 ToolNode 写 TOOL_CALL / TOOL_RESULT 事件
                if self._settings.mcp.emit_tool_events:
                    tool_node = build_tool_node(
                        tools,
                        aggregator=self._aggregator,
                    )
                    # 直接用 build_default_graph，但传入 tools；为了让 ToolNode 写事件，
                    # 我们构造一个带事件钩子的 graph
                    return self._build_graph_with_event_tools(llm, tools, tool_node)
            except Exception:  # noqa: BLE001
                _log.exception("MCP bridge failed; running LLM without tools")
                tools = []

        return build_default_graph(llm=llm, tools=tools)

    def _build_graph_with_event_tools(self, llm: Any, tools: list[Any], tool_node):
        """构造带事件钩子的 graph（tool_node 已包成事件上报版本）。"""
        from langgraph.graph import END, StateGraph

        g = StateGraph(__import__("app.models.agent_state", fromlist=["AgentState"]).AgentState)

        def _chat(state):
            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
            sys_text = "你是一个有工具调用能力的 Agent。"
            msgs_in = state.get("messages", [])
            converted: list[Any] = [SystemMessage(content=sys_text)]
            for m in msgs_in:
                role = m.get("role") if isinstance(m, dict) else None
                content = m.get("content") if isinstance(m, dict) else m.content
                if role == "user":
                    converted.append(HumanMessage(content=content))
                elif role == "assistant":
                    converted.append(AIMessage(content=content, tool_calls=m.get("tool_calls")))
                else:
                    converted.append(HumanMessage(content=str(content)))
            ai = llm.bind_tools(tools).invoke(converted)
            new_msgs = list(msgs_in) + [{"role": "assistant", "content": ai.content, "tool_calls": getattr(ai, "tool_calls", None) or []}]
            return {
                **state,
                "messages": new_msgs,
                "tool_calls": getattr(ai, "tool_calls", None) or [],
                "iter": state.get("iter", 0) + 1,
            }

        def _route(state):
            tcs = state.get("tool_calls") or []
            if state.get("iter", 0) > 20:
                return END
            return "tools" if tcs else END

        g.add_node("chat", _chat)
        g.add_node("tools", tool_node)
        g.set_entry_point("chat")
        g.add_conditional_edges("chat", _route, {"tools": "tools", END: END})
        g.add_edge("tools", "chat")
        return g.compile()

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
        try:
            await self._repo.update_status(task_id, TaskStatus.STREAMING)
            async for _ in run_agent(
                task_id=task_id,
                prompt=item.get("prompt", ""),
                aggregator=self._aggregator,
                state_manager=self._state,
                graph=self._graph,
                max_iters=self._settings.worker.default_max_iters,
            ):
                pass
            await self._aggregator.flush_all()
            await self._repo.update_status(task_id, TaskStatus.COMPLETED)
        except Exception as exc:  # noqa: BLE001
            _log.exception("agent run failed task_id=%s", task_id)
            await self._repo.update_status(task_id, TaskStatus.FAILED, error=str(exc))


async def main() -> None:
    """本地启动入口（python -m app.worker.runner）。"""
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


if __name__ == "__main__":
    asyncio.run(main())
