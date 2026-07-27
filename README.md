# mj-agent · 多 Agent 异步流式系统

一个面向多 Agent 协作的运行时骨架，基于 **FastAPI + LangGraph + Redis Stream**，
支持 **SSE 流式响应、断点续传、事件聚合、任务状态机**。

> 适用场景：长链路 LLM/工具调用、多 Agent 协同、客户端可随时断线重连的实时体验。

---

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                          Client (Browser)                        │
│                  EventSource (SSE + Last-Event-ID)               │
└──────────────────────────────┬───────────────────────────────────┘
                               │  HTTP/SSE
┌──────────────────────────────▼───────────────────────────────────┐
│                       Gateway (FastAPI)                          │
│  • StreamingResponse + SSE 帧编码                                  │
│  • ConnectionManager  (注册/心跳/超时)                              │
│  • RedisStreamSubscriber (XREAD 续读)                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │  XADD / XREAD
┌──────────────────────────────▼───────────────────────────────────┐
│                    Redis (Stream + KV + List)                     │
│  • mj:task:<id>:events  — 任务事件流                                │
│  • mj:queue:tasks       — 任务队列                                  │
│  • mj:agent_state:<id>  — Agent 状态快照                          │
└──────────────────┬─────────────────────────────────┬─────────────┘
                   │ enqueue                         │ dequeue
┌──────────────────▼────────────┐         ┌───────────▼─────────────┐
│  Business (任务/分发)          │         │  Worker (LangGraph)     │
│  • TaskService                │         │  • EventAggregator      │
│  • TaskDispatcher             │         │  • StateManager         │
└───────────────────────────────┘         │  • Agent loop           │
                                          └───────────┬─────────────┘
                                                      │ R/W
                                          ┌───────────▼─────────────┐
                                          │  DB (asyncpg / SQLAlchemy)│
                                          │  • TaskRepository       │
                                          │  • EventRepository      │
                                          └─────────────────────────┘
```

### 模块职责

| 模块 | 职责 |
| --- | --- |
| `app/gateway`   | FastAPI 路由、SSE 帧、连接管理、XREAD 订阅、断点续传 |
| `app/worker`    | LangGraph 循环、Agent 状态、事件聚合（token 合并） |
| `app/business`  | 业务层：任务创建、查询、取消、队列分发 |
| `app/common`    | 异步 Redis 客户端、asyncio 工具、日志、ID 生成 |
| `app/models`    | 任务 / 事件 / Agent 状态的数据结构 |
| `app/db`        | 异步数据库连接、Task/Event Repository |
| `config`        | YAML + 环境变量配置 |
| `tests`         | 单元测试（SSE 断点续传、事件聚合） |

---

## 2. 数据流

1. **创建任务**：`POST /api/v1/tasks` → 持久化到 DB → 入队到 Redis List `mj:queue:tasks`。
2. **消费任务**：Worker 拉取 → 更新状态 `running` → 调用 LangGraph 循环。
3. **产出事件**：节点执行结果写入 `EventAggregator` → 批量 `XADD` 到 `mj:task:<id>:events`。
4. **SSE 推送**：客户端 `GET /api/v1/tasks/{id}/events` → 通过 `XREAD` 订阅事件流 → 编码 SSE 帧下发。
5. **断线重连**：客户端带 `Last-Event-ID` 重连 → 网关从该 ID 续读。

---

## 3. 快速开始

### 3.1 环境要求

- Python ≥ 3.11
- Redis ≥ 6.2（需要 Stream 特性）
- PostgreSQL ≥ 14（或将 `database.url` 改为你偏好的异步 SQL 方言）

### 3.2 安装

```bash
python -m venv .venv
. .venv/Scripts/activate    # Windows
# source .venv/bin/activate  # macOS / Linux

pip install -r requirements.txt
```

### 3.3 配置

默认配置在 [`config/config.yaml`](file:///d:/MJ-Agent/mj-agent/config/config.yaml)；
可以通过环境变量覆盖：

| 变量 | 作用 |
| --- | --- |
| `MJ_REDIS_URL`        | Redis 连接 URL |
| `MJ_DB_URL`           | 异步 SQLAlchemy URL |
| `MJ_GATEWAY_HOST`     | 网关监听地址 |
| `MJ_GATEWAY_PORT`     | 网关端口 |
| `MJ_WORKER_CONCURRENCY` | Worker 并发度 |
| `MJ_LLM_PROVIDER`     | LLM 提供方（openai/anthropic/ollama） |
| `MJ_LLM_MODEL`        | LLM 模型名 |
| `MJ_LLM_API_KEY`      | LLM 密钥 |
| `MJ_LLM_BASE_URL`     | LLM 网关地址 |
| `MJ_LOG_LEVEL`        | 日志级别（DEBUG/INFO/WARNING） |

### 3.4 启动 Redis & PostgreSQL（Docker）

```bash
docker run -d --name mj-redis -p 6379:6379 redis:7-alpine
docker run -d --name mj-pg    -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine
```

### 3.5 启动 Worker

```bash
python -m app.worker.runner
```

### 3.6 启动 Gateway

```bash
uvicorn app.gateway.router:app --host 0.0.0.0 --port 8080
```

### 3.7 启动前端

```bash
# 推荐 Next.js（独立仓库，参见 docs/frontend.md）
# pnpm dev
```

---

## 4. API 速览

### 创建任务

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "user_id": "u_001",
  "prompt": "帮我写一首关于秋天的诗",
  "metadata": {"client": "web"},
  "stream": true
}
```

返回：

```json
{
  "task_id": "t_xxx",
  "user_id": "u_001",
  "status": "pending",
  "created_at": "...",
  "updated_at": "..."
}
```

### 查询任务

```http
GET /api/v1/tasks/{task_id}
```

### 取消任务

```http
POST /api/v1/tasks/{task_id}/cancel
```

### SSE 任务流（断点续传）

```http
GET /api/v1/tasks/{task_id}/events
Accept: text/event-stream
Last-Event-ID: 123-0          # 断线重连时携带
```

帧示例：

```
id: 1700000000000-0
event: started
data: {"event_id":"e_1","seq":1,"data":{"prompt":"..."}}

id: 1700000000001-0
event: token
data: {"event_id":"e_2","seq":2,"data":{"text":"秋"}}

: ka                           # 注释行 keepalive

id: 1700000000099-0
event: finished
data: {"event_id":"e_N","seq":N,"data":{"ok":true}}
```

前端示例（`EventSource`）：

```ts
const es = new EventSource(
  `/api/v1/tasks/${taskId}/events`,
  // 浏览器自动在断线后带 Last-Event-ID 重连
);
es.addEventListener("token", (e) => {
  const data = JSON.parse((e as MessageEvent).data);
  appendText(data.data.text);
});
es.addEventListener("finished", () => es.close());
```

---

## 5. 测试

```bash
pip install -r requirements.txt
pytest -q
```

测试覆盖：

- `test_sse_format.py` — SSE 帧编码（retry、id、event、data 多行、keepalive）
- `test_sse_resume.py` — 断点续传（全量重放 / 续读 / 续读帧）
- `test_event_aggregation.py` — 事件聚合（token 合并 / 顺序保持 / 非聚合事件立即刷新）

> 上述 SSE 与事件聚合测试使用 `fakeredis` 模拟 Redis，无需启动真实服务。

---

## 6. 目录结构

```
project/
├── app/
│   ├── gateway/        # SSE 网关（StreamingResponse、断线重连、XREAD 订阅）
│   ├── worker/         # Agent Worker（LangGraph loop、状态管理、事件聚合）
│   ├── business/       # 业务层（任务创建、队列分发）
│   ├── common/         # 异步 Redis、asyncio 工具、日志
│   ├── models/         # 状态、任务、事件结构
│   └── db/             # 异步落库、任务状态持久化
├── config/             # 配置文件
├── tests/              # 单元测试
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 7. 关键设计

### 7.1 事件聚合 (`EventAggregator`)
- `TOKEN` / `PROGRESS` 这类高频事件会被合并：每 `max_batch` 条或 `flush_interval_ms` 触发一次 `XADD`。
- 其它事件类型（`MESSAGE` / `TOOL_CALL` / `ERROR` 等）立即写入，避免延迟。

### 7.2 断点续传
- 网关 SSE 响应中每一帧都带 `id: <stream-entry-id>`。
- 客户端断线重连时携带 `Last-Event-ID`，网关把它作为 `XREAD` 的起点。

### 7.3 任务状态机
`pending → running → streaming → (completed | failed | cancelled | timeout)`，终态不可再迁移。

### 7.4 状态可恢复
Agent state 每步持久化到 Redis `mj:agent_state:<id>`，Worker 崩溃后可用 `state_manager.load` 恢复（需结合外部调度重排队）。

---

## 8. License

MIT
