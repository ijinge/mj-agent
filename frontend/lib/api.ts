/**
 * 后端 SSE 客户端
 *
 * 流程：
 *   1. POST /api/v1/tasks 创建任务 -> task_id
 *   2. EventSource(/api/v1/tasks/{id}/events) 订阅流
 *   3. 解析 SSE 帧 -> 回调 onEvent
 *   4. 断线重连：EventSource 原生带 Last-Event-ID，无需手动处理
 *
 * 当 NEXT_PUBLIC_USE_MOCK=true 或后端不可达时，调用 runMockStream 返回模拟数据。
 */
import type {
  SSEEnvelope,
  TaskCreateRequest,
  TaskResponse,
  EventType,
} from "./types";
import { runMockStream, mockCreateTask } from "./mock";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8080";
// 默认 false：连真实后端。设为 true 可在无后端时用前端 mock 离线演示。
const USE_MOCK = (process.env.NEXT_PUBLIC_USE_MOCK || "false") === "true";

export interface StreamHandlers {
  onEvent: (event: EventType, payload: any, envelope: SSEEnvelope) => void;
  onError?: (err: Error) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export async function createTask(req: TaskCreateRequest): Promise<TaskResponse> {
  if (USE_MOCK) return mockCreateTask(req);
  const r = await fetch(`${API_BASE}/api/v1/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) {
    throw new Error(`create task failed: ${r.status} ${r.statusText}`);
  }
  return r.json();
}

export interface StreamHandle {
  close: () => void;
  promise: Promise<void>;
}

export function subscribeTask(
  taskId: string,
  handlers: StreamHandlers,
  lastEventId?: string,
): StreamHandle {
  if (USE_MOCK) {
    return runMockStream(taskId, handlers, lastEventId);
  }
  // 真实后端：EventSource 自带断线重连
  const url = new URL(`${API_BASE}/api/v1/tasks/${encodeURIComponent(taskId)}/events`);
  if (lastEventId) {
    // EventSource 会自动把 Last-Event-ID 放在 header
  }
  const es = new EventSource(url.toString(), { withCredentials: false });
  es.addEventListener("open", () => handlers.onOpen?.());

  // 通用：按 event name 分发
  const dispatch = (e: MessageEvent) => {
    const envelope: SSEEnvelope = {
      id: e.lastEventId,
      event: e.type,
      data: e.data,
    };
    let parsed: any = {};
    try {
      parsed = e.data ? JSON.parse(e.data) : {};
    } catch {
      parsed = { raw: e.data };
    }
    handlers.onEvent(e.type as EventType, parsed, envelope);
  };

  // 监听常见事件名
  const eventNames: string[] = [
    "started",
    "token",
    "message",
    "tool_call",
    "tool_result",
    "thinking",
    "progress",
    "error",
    "finished",
    "done",
  ];
  for (const n of eventNames) {
    es.addEventListener(n, dispatch as EventListener);
  }
  // 未识别事件兜底
  es.onmessage = dispatch as EventListener;

  es.addEventListener("error", (e) => {
    handlers.onError?.(new Error("SSE connection error"));
  });

  const promise = new Promise<void>((resolve) => {
    es.addEventListener("done", () => {
      handlers.onClose?.();
      es.close();
      resolve();
    });
    // finished 也视作结束
    es.addEventListener("finished", () => {
      handlers.onClose?.();
      es.close();
      resolve();
    });
  });

  return {
    close: () => es.close(),
    promise,
  };
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  if (USE_MOCK) {
    return {
      task_id: taskId,
      user_id: "mock-user",
      status: "completed",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      last_event_seq: 0,
      metadata: {},
    };
  }
  const r = await fetch(`${API_BASE}/api/v1/tasks/${encodeURIComponent(taskId)}`);
  if (!r.ok) {
    throw new Error(`get task failed: ${r.status}`);
  }
  return r.json();
}

export async function cancelTask(taskId: string): Promise<void> {
  if (USE_MOCK) return;
  const r = await fetch(`${API_BASE}/api/v1/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
  });
  if (!r.ok) {
    throw new Error(`cancel task failed: ${r.status}`);
  }
}
