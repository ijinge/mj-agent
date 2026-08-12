"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { InputPanel } from "./InputPanel";
import { OutputPanel } from "./OutputPanel";
import { createTask, subscribeTask } from "@/lib/api";
import { tryParseJson, uuid } from "@/lib/utils";
import type { EventType, RunStatus, ToolCallEntry } from "@/lib/types";

const DEFAULT_GAME_ID = "";
const DEFAULT_GAME_STATE = "";
const DEFAULT_QUESTION = "";

export function HomePage() {
  const [gameId, setGameId] = useState(DEFAULT_GAME_ID);
  const [gameState, setGameState] = useState(DEFAULT_GAME_STATE);
  const [question, setQuestion] = useState(DEFAULT_QUESTION);

  const [status, setStatus] = useState<RunStatus>("idle");
  const [taskId, setTaskId] = useState<string | undefined>(undefined);
  const [streamedText, setStreamedText] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolCallEntry[]>([]);
  const startedAtRef = useRef<number | undefined>(undefined);
  const [finishedAt, setFinishedAt] = useState<number | undefined>(undefined);
  const handleRef = useRef<{ close: () => void } | null>(null);
  // tool_call.id -> 内部 ToolCallEntry.id 映射
  const callMapRef = useRef<Map<string, string>>(new Map());

  const parsedState = useMemo(() => {
    const r = tryParseJson(gameState);
    return r.ok ? r.value : null;
  }, [gameState]);

  const handleSubmit = useCallback(async () => {
    if (!parsedState) return;
    setStreamedText("");
    setToolCalls([]);
    callMapRef.current.clear();
    setStatus("streaming");
    setFinishedAt(undefined);
    startedAtRef.current = Date.now();

    try {
      const task = await createTask({
        user_id: "web-user",
        game_id: gameId.trim(),
        prompt: buildPrompt(question, gameId),
        metadata: {
          game_state: parsedState,
          question,
        },
        stream: true,
      });
      setTaskId(task.task_id);

      const handle = subscribeTask(task.task_id, {
        onOpen: () => {
          setStatus("streaming");
        },
        onEvent: (event: EventType, payload: any) => {
          handleEvent(event, payload, setStreamedText, setToolCalls, callMapRef);
        },
        onError: (err) => {
          console.error("stream error", err);
          setStatus("error");
        },
        onClose: () => {
          setFinishedAt(Date.now());
          setStatus((prev) => (prev === "error" ? "error" : "done"));
        },
      });
      handleRef.current = handle;
    } catch (e) {
      console.error(e);
      setStatus("error");
    }
  }, [gameId, parsedState, question]);

  const handleClear = useCallback(() => {
    handleRef.current?.close();
    handleRef.current = null;
    setStreamedText("");
    setToolCalls([]);
    setStatus("idle");
    setTaskId(undefined);
    setFinishedAt(undefined);
    startedAtRef.current = undefined;
    setGameId(DEFAULT_GAME_ID);
    setGameState(DEFAULT_GAME_STATE);
    setQuestion(DEFAULT_QUESTION);
  }, []);

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-4 py-6 lg:px-8 lg:py-8">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:gap-6">
        {/* 左：输入 */}
        <InputPanel
          gameId={gameId}
          onGameIdChange={setGameId}
          gameState={gameState}
          onGameStateChange={setGameState}
          question={question}
          onQuestionChange={setQuestion}
          onSubmit={handleSubmit}
          onClear={handleClear}
          loading={status === "streaming"}
        />

        {/* 右：输出 */}
        <OutputPanel
          status={status}
          taskId={taskId}
          startedAt={startedAtRef.current}
          finishedAt={finishedAt}
          streamedText={streamedText}
          toolCalls={toolCalls}
        />
      </div>
    </main>
  );
}

function buildPrompt(question: string, gameId: string): string {
  return [
    `【地方麻将类型 ID】${gameId.trim() || "(未填)"}`,
    `【用户提问】${question || "(未填)"}`,
  ].join("\n\n");
}

function handleEvent(
  event: EventType,
  payload: any,
  setStreamedText: (updater: (prev: string) => string) => void,
  setToolCalls: (updater: (prev: ToolCallEntry[]) => ToolCallEntry[]) => void,
  callMap: React.MutableRefObject<Map<string, string>>,
): void {
  switch (event) {
    case "started":
      break;
    case "token": {
      const text = payload?.data?.text;
      if (typeof text === "string") {
        setStreamedText((prev) => prev + text);
      }
      break;
    }
    case "message": {
      const text = payload?.data?.text ?? payload?.data?.content;
      if (typeof text === "string") {
        setStreamedText((prev) => prev + text);
      }
      break;
    }
    case "tool_call": {
      const name: string = payload?.data?.name ?? "unknown";
      const args: Record<string, unknown> = payload?.data?.args ?? {};
      const remoteId: string | undefined = payload?.data?.id;
      const internalId = uuid();
      if (remoteId) callMap.current.set(remoteId, internalId);
      const entry: ToolCallEntry = {
        id: internalId,
        server: name.includes(":") ? name.split(":")[0] : "default",
        name,
        args,
        status: "calling",
        startedAt: Date.now(),
      };
      setToolCalls((prev) => [...prev, entry]);
      break;
    }
    case "tool_result": {
      const remoteId: string | undefined = payload?.data?.tool_call_id;
      const result = payload?.data?.content;
      const internalId = remoteId ? callMap.current.get(remoteId) : undefined;
      setToolCalls((prev) =>
        prev.map((t) =>
          t.id === internalId
            ? {
                ...t,
                result,
                status: "ok",
                finishedAt: Date.now(),
              }
            : t,
        ),
      );
      break;
    }
    case "thinking": {
      const text = payload?.data?.text;
      if (typeof text === "string") {
        setStreamedText((prev) => prev + `\n> ${text}\n`);
      }
      break;
    }
    case "progress":
      break;
    case "finished":
      break;
    case "error": {
      const msg: string = payload?.data?.message ?? "unknown error";
      setStreamedText((prev) => prev + `\n\n> ⚠ **错误**：${msg}\n`);
      break;
    }
    default:
      void event;
      break;
  }
}
