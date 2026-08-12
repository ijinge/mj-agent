"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { StatusBar } from "./StatusBar";
import { MarkdownView } from "./MarkdownView";
import { ToolCallTimeline } from "./ToolCallTimeline";
import type { ToolCallEntry, RunStatus } from "@/lib/types";

export function OutputPanel({
  status,
  taskId,
  startedAt,
  finishedAt,
  streamedText,
  toolCalls,
  className,
}: {
  status: RunStatus;
  taskId?: string;
  startedAt?: number;
  finishedAt?: number;
  streamedText: string;
  toolCalls: ToolCallEntry[];
  className?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // 流式输出时自动滚到底
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (dist < 200) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [streamedText, toolCalls.length, status]);

  return (
    <section
      className={cn(
        "flex flex-col gap-4 rounded-lg border border-silk bg-paper p-5",
        className,
      )}
    >
      <StatusBar
        status={status}
        taskId={taskId}
        startedAt={startedAt}
        finishedAt={finishedAt}
      />

      {/* 流式输出 */}
      <div
        ref={scrollRef}
        className={cn(
          "min-h-[280px] flex-1 overflow-y-auto rounded border border-silk/60 bg-paper-deep/20 p-4",
        )}
      >
        <MarkdownView content={streamedText} streaming={status === "streaming"} />
      </div>

      {/* 工具调用状态 */}
      <ToolCallTimeline tools={toolCalls} />
    </section>
  );
}
