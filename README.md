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

![alt text](8f131def8c02ac829ab30f137346f6eb-1.png)

### 模块职责

| 模块 | 职责 |
| --- | --- |
| `app/gateway`   | FastAPI 路由、SSE 帧、连接管理、XREAD 订阅、断点续传 |
| `app/worker`    | LangGraph 循环、Agent 状态、事件聚合（token 合并） |
| `app/worker/mcp`| MCP 客户端、工具注册、MCP↔LangChain 桥接、ToolNode 事件 |
| `app/business`  | 业务层：任务创建、查询、取消、队列分发 |
| `app/common`    | 异步 Redis 客户端、asyncio 工具、日志、ID 生成 |
| `app/models`    | 任务 / 事件 / Agent 状态的数据结构 |
| `app/db`        | 异步数据库连接、Task/Event Repository |
| `config`        | YAML + 环境变量配置 |
| `tests`         | 单元测试（SSE 断点续传、事件聚合、MCP 适配） |

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
- 可选：Docker / Docker Compose（用于跑 redis + postgres）

### 3.2 一键环境搭建（推荐）

**Linux / macOS：**

```bash
./scripts/setup.sh            # 创建 .venv + 装 dev 依赖 + 跑测试
./scripts/setup.sh --base     # 仅装生产依赖（无测试/lint）
./scripts/setup.sh --recreate # 删除 .venv 后重建
```

**Windows PowerShell：**

```powershell
.\scripts\setup.ps1            # 创建 .venv + 装 dev 依赖 + 跑测试
.\scripts\setup.ps1 -Base      # 仅装生产依赖
.\scripts\setup.ps1 -Recreate  # 删除 .venv 后重建
```

### 3.3 手动安装

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### 3.4 验证安装

```bash
python -c "import fastapi, langgraph, mcp; print('all ok')"
pytest -q
```

### 3.5 配置

默认配置在 [`config/config.yaml`](file:///d:/MJ-Agent/mj-agent/config/config.yaml)；
可以复制 [`.env.example`](file:///d:/MJ-Agent/mj-agent/.env.example) 为 `.env` 后通过环境变量覆盖。

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

### 3.6 启动 Redis & PostgreSQL（Docker / 远端服务器）

**典型部署**：redis + postgres 跑在远端服务器，本机跑 gateway / worker / 前端。
把 [`docker-compose.yml`](file:///d:/MJ-Agent/mj-agent/docker-compose.yml) 拷贝到服务器上（只部署这两个服务，不需要 Dockerfile），然后：

#### 在服务器上

```bash
# 1) 上传 docker-compose.yml 后：
docker compose up -d

# 2) 确认服务正常
docker compose ps
docker compose logs -f

# 3) 防火墙放行 6379 / 5432（示例：ufw）
sudo ufw allow from <本机IP> to any port 6379 proto tcp
sudo ufw allow from <本机IP> to any port 5432 proto tcp
sudo ufw reload
```

启动后服务器暴露的端口：

- **Redis**    -> `<server-ip>:6379`
- **Postgres** -> `<server-ip>:5432`，`user=postgres` / `pass=postgres` / `db=mjagent`

#### 在本机

复制 [`.env.example`](file:///d:/MJ-Agent/mj-agent/.env.example) 为 `.env`，把 `<server-ip>` 替换为服务器实际 IP：

```bash
cp .env.example .env
# 把下面两行的 127.0.0.1 改成 <server-ip>：
MJ_REDIS_URL=redis://<server-ip>:6379/0
MJ_DB_URL=postgresql+asyncpg://postgres:postgres@<server-ip>:5432/mjagent
```

或者直接改 [`config/config.yaml`](file:///d:/MJ-Agent/mj-agent/config/config.yaml) 的 `redis.url` / `database.url` 字段（env 变量优先）。

然后本机照常启动：

```bash
# Gateway（监听 0.0.0.0:8080）
.venv/bin/uvicorn app.gateway.router:build_app --factory --host 0.0.0.0 --port 8080
# 或 Windows：.venv\Scripts\uvicorn app.gateway.router:build_app --factory --host 0.0.0.0 --port 8080

# Worker（另开一个终端）
.venv/bin/python -m app.worker.runner
# 或 Windows：.venv\Scripts\python -m app.worker.runner

# 本机自检
curl http://127.0.0.1:8080/healthz
```

#### 常用 Docker 命令

```bash
docker compose up -d        # 启动
docker compose down         # 停止
docker compose down -v      # 停止并清空数据
docker compose logs -f      # 跟踪日志
docker compose ps           # 查看状态
```

> **安全提示**：远端部署时 `postgres` 默认密码是 `postgres`，redis 无鉴权。
> 生产环境请务必：
> 1. 修改 `docker-compose.yml` 里 `POSTGRES_PASSWORD` 为强密码，并同步修改 `MJ_DB_URL`；
> 2. 给 redis 加 `requirepass`（在 `command` 里加 `--requirepass yourpass`，并把 `MJ_REDIS_URL` 改成 `redis://:yourpass@<server-ip>:6379/0`）；
> 3. 用防火墙（ufw / iptables / 安全组）限制 6379 / 5432 仅允许本机 IP 访问。
> 上面 compose 里的防火墙示例就是只放行你本机 IP 的最小权限方案。

#### 不想用 compose？直接 docker run 也行

```bash
docker run -d --name mj-redis -p 6379:6379 redis:7-alpine
docker run -d --name mj-pg    -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine
```

#### 全跑在本机？

把 compose 里 `ports` 改回 `127.0.0.1:6379:6379` / `127.0.0.1:5432:5432`，
然后 `.env` 保持默认的 `127.0.0.1` 即可，本机直接 `uvicorn ...` / `python -m app.worker.runner` 就能连上。

### 3.7 启动 Worker

```bash
# 在 .venv 下直接 python
python -m app.worker.runner
```

### 3.8 启动 Gateway

```bash
# 方式 1：uvicorn + --factory（推荐，build_app 内部自动初始化 Redis/DB）
uvicorn app.gateway.router:build_app --factory --host 0.0.0.0 --port 8080
```

### 3.9 启动前端

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

## 8. MCP 工具接入

Worker 通过 [Model Context Protocol](https://modelcontextprotocol.io/) 接入任意外部工具服务，
通过 `app/worker/mcp/` 子模块完成"连接 → 发现 → 桥接 → 调用"全流程。

### 8.1 配置示例（`config/config.yaml`）

```yaml
mcp:
  enabled: true
  emit_tool_events: true          # 把 tool_call / tool_result 写回 SSE 流
  allowlist: []                   # 留空 = 全部
  denylist: []
  servers:
    # 本地 stdio 启动官方 filesystem server
    - name: filesystem
      transport: stdio
      enabled: true
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "./workspace"]
      env: {}

    # 远端 SSE MCP server
    - name: remote-search
      transport: sse
      enabled: true
      url: https://mcp.example.com/sse
      headers:
        Authorization: "Bearer xxx"

    # 远端 streamable_http MCP server
    - name: remote-tools
      transport: streamable_http
      enabled: false
      url: https://mcp.example.com/mcp
```

### 8.2 工具调用流程

1. Worker 启动时按 `servers` 列表初始化多个 `ClientSession`（[client.py](file:///d:/MJ-Agent/mj-agent/app/worker/mcp/client.py)）
2. 调用 `session.list_tools()`，把工具注册到 `ToolRegistry`（[registry.py](file:///d:/MJ-Agent/mj-agent/app/worker/mcp/registry.py)）
3. 通过 `mcp_to_langchain_tools()` 把 MCP 工具桥接为 `StructuredTool`（[adapter.py](file:///d:/MJ-Agent/mj-agent/app/worker/mcp/adapter.py)）
4. LangGraph 用 `llm.bind_tools(tools)` + `ToolNode` 实现自动 tool_call 循环
5. 每次工具调用前后下发 `TOOL_CALL` / `TOOL_RESULT` 事件（[tool_node.py](file:///d:/MJ-Agent/mj-agent/app/worker/mcp/tool_node.py)）

### 8.3 工具命名空间

为避免多 server 撞名，所有工具以 `<server_name>:<tool_name>` 形式暴露给 LLM，例如：
- `filesystem:read_file`
- `filesystem:write_file`
- `remote-search:web_search`

可在 `allowlist` / `denylist` 中按限定名裁剪可用工具。

### 8.4 不依赖 mcp SDK 的回退

如果 `mcp` / `langchain-mcp-adapters` 未安装或官方 adapter 不可用，
[mcp_to_langchain_tools](file:///d:/MJ-Agent/mj-agent/app/worker/mcp/adapter.py#L122-L168) 会回退到本地手写包装：
按 registry 注册的 schema 构造 `StructuredTool`，调用 `mgr.call_tool()` 直接走 `ClientSession.call_tool`。
这意味着即使在简化环境（无 mcp）下，桥接层仍能工作（前提是手动 mock ClientSession）。

---

## 9. License

MIT
