"use client";

import { cn, shortId } from "@/lib/utils";
import type { RunStatus } from "@/lib/types";

const STATUS_MAP: Record<RunStatus, { label: string; cn: string }> = {
  idle: { label: "就绪", cn: "status-dot--idle" },
  streaming: { label: "流式中", cn: "status-dot--streaming" },
  done: { label: "已完成", cn: "status-dot--done" },
  error: { label: "异常", cn: "status-dot--error" },
};

export function StatusBar({
  status,
  taskId,
  startedAt,
  finishedAt,
  className,
}: {
  status: RunStatus;
  taskId?: string;
  startedAt?: number;
  finishedAt?: number;
  className?: string;
}) {
  const meta = STATUS_MAP[status];
  const duration =
    startedAt && finishedAt
      ? finishedAt - startedAt
      : startedAt
        ? Date.now() - startedAt
        : null;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 rounded border border-silk bg-paper-deep/50 px-4 py-2.5",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("status-dot", meta.cn)} />
        <span className="text-sm font-medium text-ink">{meta.label}</span>
      </div>

      <div className="flex items-center gap-4 font-mono text-xs text-ink-soft">
        {taskId && (
          <span className="flex items-center gap-1.5">
            <span className="text-ink-soft/70">ID</span>
            <span className="rounded border border-silk bg-paper px-1.5 py-0.5 text-ink">
              {shortId(taskId, 8, 4)}
            </span>
          </span>
        )}
        {duration !== null && (
          <span className="flex items-center gap-1.5">
            <span className="text-ink-soft/70">耗时</span>
            <span className="text-jade">{(duration / 1000).toFixed(1)}s</span>
          </span>
        )}
      </div>
    </div>
  );
}
