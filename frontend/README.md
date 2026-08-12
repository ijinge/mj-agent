# 雀智 · Mahjong Insight · Frontend

麻将复盘 / 听牌分析 / 策略问答 — Next.js 14 + TypeScript + Tailwind CSS。

> 后端：[`../app/`](../app)（FastAPI SSE Gateway）。
> 设计：东方纸墨 · 玉石质感（jade `#1F4D3E` + cinnabar `#C73E3A`，衬线中文 + 纸纹背景）。

---

## 快速开始

```bash
# 1. 安装依赖（推荐 pnpm；亦可用 npm / yarn）
pnpm install
# 或
npm install

# 2. 复制环境变量
cp .env.example .env.local

# 3. 启动
pnpm dev
# 打开 http://localhost:3000
```

打开页面后无需后端即可演示：前端内置 mock 流（开关：`NEXT_PUBLIC_USE_MOCK=true`）。
当后端 `/api/v1/tasks` 可达时切换为真实 SSE 消费。

## 接入后端

修改 `.env.local`：

```ini
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8080
NEXT_PUBLIC_USE_MOCK=false
```

后端必须先启动（见根目录 [README §3.7 启动 Worker](../README.md#37-启动-worker) 与
[§3.8 启动 Gateway](../README.md#38-启动-gateway)）。

## 页面布局

```
┌────────────────────────────────────────────────────────────┐
│ Header：雀智 · Mahjong Insight  + 主题切换 + 印章          │
├────────────────────────────────────────────────────────────┤
│ PageIntro：复盘 · 听牌 · 策略问答                           │
├──────────────────┬─────────────────────────────────────────┤
│ InputPanel (5/12)│ OutputPanel (7/12)                      │
│ 一. 牌局 ID      │ 状态栏 / 进度条                          │
│ 二. 场面状态 JSON│ 上下文摘要                                │
│   - 语法高亮     │ 流式输出 (markdown)                       │
│   - 示例填充     │ 工具调用时间线（折叠）                    │
│ 三. 用户提问     │                                          │
│   - 推荐提问     │                                          │
│ [清空] [开始分析]│                                          │
└──────────────────┴─────────────────────────────────────────┘
```

## 目录结构

```
frontend/
├── app/
│   ├── layout.tsx          # 字体注入、metadata、ThemeProvider
│   ├── providers.tsx       # ThemeProvider
│   ├── page.tsx            # 入口，渲染 HomePage
│   └── globals.css         # 设计令牌 + 纸纹 + 流式光标
├── components/
│   ├── Header.tsx          # 顶部栏 + 主题切换 + 麻将牌 SVG
│   ├── HomePage.tsx        # 主页逻辑（state + 流订阅）
│   ├── InputPanel.tsx      # 左侧输入表单（一/二/三 序号）
│   ├── StateEditor.tsx     # JSON 编辑器（带校验 + 示例填充）
│   ├── OutputPanel.tsx     # 右侧输出容器
│   ├── StatusBar.tsx       # 状态指示灯 + 任务 ID + 耗时
│   ├── ContextSummary.tsx  # 输入上下文摘要
│   ├── MarkdownView.tsx    # 流式 markdown 渲染
│   └── ToolCallTimeline.tsx# 工具调用时间线（折叠 + 展开参数/结果）
├── lib/
│   ├── api.ts              # SSE 客户端封装（EventSource + mock 降级）
│   ├── mock.ts             # mock 数据：模拟一次完整复盘流程
│   ├── presets.ts          # 场面状态预设（标准四人 / 血流 / 川麻）
│   ├── types.ts            # 与后端对齐的类型定义
│   └── utils.ts            # cn / formatTime / parseQualifiedName / uuid
├── public/                 # 静态资源
├── next.config.mjs
├── tailwind.config.ts
├── postcss.config.mjs
├── tsconfig.json
├── package.json
├── .env.example
├── .gitignore
└── README.md
```

## SSE 事件约定

| event 名称 | 载荷 `data` | 前端处理 |
| --- | --- | --- |
| `started`     | `{ event_id, seq, data: { prompt, max_iters } }` | 仅记录元信息 |
| `token`       | `{ data: { text, node } }` | 累加到流式正文 |
| `message`     | `{ data: { text / content } }` | 同上 |
| `thinking`    | `{ data: { text } }` | 渲染为引用块 |
| `tool_call`   | `{ data: { name, args, id } }` | 追加到时间线（`calling`） |
| `tool_result` | `{ data: { name, tool_call_id, content } }` | 按 `tool_call_id` 关联，更新为 `ok` |
| `progress`    | `{ data }` | 不渲染 |
| `error`       | `{ data: { message } }` | 渲染为错误引用 + 状态置为 error |
| `finished`    | `{ data: { ok } }` | 关闭流，状态置为 done |

## 未来扩展

- **MCP 工具接入**：后端 `app/worker/mcp/` 已支持 stdio / sse / streamable_http，
  前端 `ToolCallTimeline` 已预留参数/结果展开。后续接入时只需：
  1. 在 `lib/api.ts` 中真实 EventSource（当前已实现）
  2. 在 `config/config.yaml` 的 `mcp.servers` 添加工具服务
  3. 调整 mock 脚本与 LLM 提示词

- **多任务/历史**：可将 `taskId` + `streamedText` 持久化到 localStorage。
- **多人协作**：在 ContextSummary 增加「对手视角」选项。

## 设计原则

- **克制用色**：jade 与 cinnabar 仅用于强调、CTA、状态指示；正文一律 ink/silk。
- **纸感背景**：浅色主题有细噪点纹理（SVG feTurbulence），深色主题反向。
- **衬线中文**：标题用 Noto Serif SC（古典），正文用 Noto Sans SC（清晰）。
- **序号仪式感**：左侧用中文数字 一/二/三，强调「复盘 / 分析」的过程感。
- **响应式**：桌面两栏，移动端堆叠；中间装订线 lg+ 才显示。

## License

MIT
