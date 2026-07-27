"""MJ-Agent: 多 Agent 异步流式系统。

架构层次：
- gateway:    SSE 网关（FastAPI StreamingResponse + 断点续传）
- worker:     Agent Worker（LangGraph 循环 + 事件聚合）
- business:   业务层（任务创建 + 队列分发）
- common:     通用能力（异步 Redis、asyncio 工具、日志）
- models:     数据模型（任务、事件、状态）
- db:         持久化（异步数据库访问、状态落库）
"""

__version__ = "0.1.0"
