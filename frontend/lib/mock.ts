/**
 * Mock 模拟流：当后端不可达或 NEXT_PUBLIC_USE_MOCK=true 时使用。
 * 模拟一个真实的麻将对局分析过程：started → 多个 token → tool_call → tool_result → finished。
 */
import type { TaskCreateRequest, TaskResponse, EventType } from "./types";
import type { StreamHandle, StreamHandlers } from "./api";
import { uuid } from "./utils";

const SCRIPT = `## 牌局速览

| 项目 | 状态 |
| --- | --- |
| 局数 | 东三局 1 本场 |
| 巡目 | 5 巡 |
| 宝牌 | 🀙 🀔 |

听牌候选按 **向听数** 升序：

- **雀头两面**：{4m, 7m} → 两面待 3m/6m（**两听**）
- **嵌张**：{5p, 7p} → 嵌 6p（**一向听**）
- **双碰**：{🀀🀀, 🀁🀁} → 平和断幺（**两听**）

> 当前最佳选择：摸切 8p，向听不变；切 7p 推进两听候选，但**不破坏**双碰役牌。

---

### 建议（按优先级）

1. 摸 **3m / 6m** 时切 8p → 听 **🀇🀈** 两面
2. 摸 **🀀 / 🀁** 时切对子保持 → 听 **对对和**（役牌）
3. 摸 **6p** 时切 5p → 听 **5m/8m + 嵌 6p** 三面

**综合胜率：约 32%**（基于剩余 60 张牌 + 河底 14 张可见）
`;

const TOOL_CALLS = [
  {
    name: "mj:read_hand",
    args: { player: "self", seat: 0 },
    result: { tiles: ["1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", "5p", "7p", "🀀", "🀀"], shanten: 1 },
  },
  {
    name: "mj:scan_tenpai",
    args: { candidates: ["3m", "6m", "6p", "🀀"] },
    result: { matrix: [[0.32, 0.18, 0.21, 0.14]], best: 0 },
  },
  {
    name: "mj:estimate_winrate",
    args: { shanten: 1, dora: ["🀙", "🀔"] },
    result: { winrate: 0.32, sd: 0.04 },
  },
];

export async function mockCreateTask(req: TaskCreateRequest): Promise<TaskResponse> {
  await sleep(150);
  return {
    task_id: `t_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    user_id: req.user_id,
    status: "streaming",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    last_event_seq: 0,
    metadata: { ...req.metadata, game_id: req.game_id },
  };
}

export function runMockStream(
  taskId: string,
  handlers: StreamHandlers,
  _lastEventId?: string,
): StreamHandle {
  let cancelled = false;
  const allEvents: { event: EventType; data: any }[] = [];
  let seq = 0;
  const eid = () => `e_${++seq}`;
  const sid = (streamId: string) => streamId;

  // 生成完整事件序列
  allEvents.push({ event: "started", data: { event_id: eid(), seq, data: { prompt: "[mock] " } } });

  // 第一个 token 段落
  pushTokens(allEvents, SCRIPT.split(""), 12, 25, () => eid(), () => ++seq);

  // 工具调用
  for (const tc of TOOL_CALLS) {
    allEvents.push({
      event: "tool_call",
      data: { event_id: eid(), seq: ++seq, data: { name: tc.name, args: tc.args, id: sid(`call_${seq}`) } },
    });
    allEvents.push({
      event: "tool_result",
      data: {
        event_id: eid(),
        seq: ++seq,
        data: { name: tc.name, tool_call_id: `call_${seq - 1}`, content: tc.result },
      },
    });
    // 工具之间再来一段 token
    pushTokens(allEvents, "\n\n".split(""), 80, 120, () => eid(), () => ++seq);
  }

  // 第二段 token（结论）
  const tail = SCRIPT.split("").slice(SCRIPT.length / 2);
  pushTokens(allEvents, tail, 18, 35, () => eid(), () => ++seq);

  allEvents.push({ event: "finished", data: { event_id: eid(), seq: ++seq, data: { ok: true } } });

  handlers.onOpen?.();

  const promise = (async () => {
    try {
      for (const ev of allEvents) {
        if (cancelled) break;
        const envelope = {
          id: `mock-${seq}`,
          event: ev.event,
          data: JSON.stringify(ev.data),
        };
        handlers.onEvent(ev.event, ev.data, envelope);
        // 不同事件类型不同间隔
        if (ev.event === "tool_call" || ev.event === "tool_result") {
          await sleep(280);
        } else if (ev.event === "started" || ev.event === "finished") {
          await sleep(150);
        } else {
          await sleep(20 + Math.random() * 40);
        }
      }
      handlers.onClose?.();
    } catch (e) {
      handlers.onError?.(e instanceof Error ? e : new Error(String(e)));
    }
  })();

  return {
    close: () => {
      cancelled = true;
    },
    promise,
  };
}

function pushTokens(
  out: { event: EventType; data: any }[],
  chars: string[],
  minDelay: number,
  maxDelay: number,
  makeEid: () => string,
  makeSeq: () => number,
) {
  let buffer = "";
  let lastFlush = 0;
  for (let i = 0; i < chars.length; i++) {
    buffer += chars[i];
    const now = Date.now();
    if (buffer.length >= 3 + Math.floor(Math.random() * 4) || now - lastFlush > 40) {
      out.push({
        event: "token",
        data: { event_id: makeEid(), seq: makeSeq(), data: { text: buffer, node: "chat" } },
      });
      buffer = "";
      lastFlush = now;
    }
  }
  if (buffer) {
    out.push({
      event: "token",
      data: { event_id: makeEid(), seq: makeSeq(), data: { text: buffer, node: "chat" } },
    });
  }
  // 给一个 0 范围数字，避免未使用
  void minDelay;
  void maxDelay;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
