/** 前端类型定义（与后端 app/models/* 对齐）。 */

export type RunStatus = "idle" | "streaming" | "done" | "error";

export type EventType =
  | "started"
  | "token"
  | "message"
  | "tool_call"
  | "tool_result"
  | "thinking"
  | "progress"
  | "error"
  | "finished";

export interface SSEEnvelope {
  id: string; // SSE event id (= Redis Stream entry id, e.g. "1700000000-0")
  event: string; // SSE event 名称
  data: string; // SSE data 原文 (JSON)
  retry?: number;
}

export interface TaskCreateRequest {
  user_id: string;
  game_id: string;
  prompt: string;
  metadata: Record<string, unknown>;
  stream: boolean;
}

export interface TaskResponse {
  task_id: string;
  user_id: string;
  status: "pending" | "running" | "streaming" | "completed" | "failed" | "cancelled" | "timeout";
  created_at: string;
  updated_at: string;
  error?: string | null;
  last_event_seq: number;
  metadata: Record<string, unknown>;
}

export interface TokenPayload {
  event_id?: string;
  seq?: number;
  data: {
    text?: string;
    node?: string;
    tool_calls?: unknown[];
    [k: string]: unknown;
  };
}

export interface ToolCallPayload {
  event_id?: string;
  seq?: number;
  data: {
    name?: string;
    args?: Record<string, unknown>;
    id?: string;
  };
}

export interface ToolResultPayload {
  event_id?: string;
  seq?: number;
  data: {
    name?: string;
    tool_call_id?: string;
    content?: unknown;
  };
}

export interface StartedPayload {
  event_id?: string;
  seq?: number;
  data: {
    prompt?: string;
    max_iters?: number;
  };
}

export interface ErrorPayload {
  event_id?: string;
  seq?: number;
  data: { message?: string };
}

export interface FinishedPayload {
  event_id?: string;
  seq?: number;
  data: { ok?: boolean };
}

/** 工具调用（前端 UI 用） */
export interface ToolCallEntry {
  id: string; // 内部生成的 uuid
  server: string; // 从 qualified name 解析
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
  status: "calling" | "ok" | "error";
  startedAt: number;
  finishedAt?: number;
}

/** 场面状态（用户输入的 game_state JSON） */
export interface GameState {
  variant?: string;            // 标准四人 / 血流成河 / 川麻
  round?: string;              // 东一局 / 南二局 ...
  tiles_remaining?: number;
  players?: Array<{
    id: string;
    name: string;
    seat: number;               // 0:东 1:南 2:西 3:北
    score: number;
    hand?: string[];           // 手牌
    discards?: string[];       // 弃牌
    melds?: unknown[];
  }>;
  dora_indicators?: string[];
  [k: string]: unknown;
}
