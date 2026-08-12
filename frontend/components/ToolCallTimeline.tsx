"use client";

import { useState } from "react";
import { ChevronDown, Wrench, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { cn, parseQualifiedName } from "@/lib/utils";
import type { ToolCallEntry } from "@/lib/types";

export function ToolCallTimeline({
  tools,
  className,
}: {
  tools: ToolCallEntry[];
  className?: string;
}) {
  const [open, setOpen] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (tools.length === 0) {
    return (
      <div
        className={cn(
          "rounded border border-dashed border-silk bg-paper/30 px-4 py-3 text-sm text-ink-soft",
          className,
        )}
      >
        <div className="flex items-center gap-2">
          <Wrench className="h-3.5 w-3.5 text-ink-soft/60" />
          <span className="text-xs">工具调用</span>
        </div>
        <p className="mt-1.5 text-xs text-ink-soft/80">
          当前任务未调用工具。
        </p>
      </div>
    );
  }

  const success = tools.filter((t) => t.status === "ok").length;
  const failed = tools.filter((t) => t.status === "error").length;

  return (
    <div
      className={cn(
        "overflow-hidden rounded border border-silk bg-paper/70",
        className,
      )}
    >
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors hover:bg-paper-deep/50"
      >
        <div className="flex items-center gap-2">
          <Wrench className="h-3.5 w-3.5 text-jade" />
          <span className="text-xs text-ink-soft">工具调用</span>
          <span className="rounded border border-silk bg-paper px-1.5 py-0.5 text-[10px] text-ink">
            {tools.length}
          </span>
          {success > 0 && (
            <span className="text-[10px] text-jade">✓ {success}</span>
          )}
          {failed > 0 && (
            <span className="text-[10px] text-cinnabar">✕ {failed}</span>
          )}
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-ink-soft transition-transform",
            open ? "rotate-180" : "rotate-0",
          )}
        />
      </button>

      {open && (
        <ol className="border-t border-silk">
          {tools.map((t, i) => {
            const { server, name } = parseQualifiedName(t.name);
            const isOpen = expanded[t.id] ?? false;
            return (
              <li
                key={t.id}
                className="border-b border-silk/60 last:border-b-0"
              >
                <button
                  onClick={() =>
                    setExpanded((s) => ({ ...s, [t.id]: !isOpen }))
                  }
                  className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left hover:bg-paper-deep/40"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    {statusIcon(t.status)}
                    <div className="min-w-0">
                      <div className="flex items-baseline gap-2">
                        <span className="text-sm font-medium text-jade">
                          {name}
                        </span>
                        <span className="font-mono text-[10px] text-ink-soft">
                          {server}
                        </span>
                      </div>
                      <div className="font-mono text-[10px] text-ink-soft">
                        {summarizeArgs(t.args)}
                      </div>
                    </div>
                  </div>
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-ink-soft transition-transform",
                      isOpen ? "rotate-180" : "rotate-0",
                    )}
                  />
                </button>
                {isOpen && (
                  <div className="space-y-2 border-t border-silk/60 bg-paper-deep/30 px-4 py-3">
                    <KV label="参数" value={t.args} mono />
                    <KV
                      label="结果"
                      value={t.result ?? "(执行中…)"}
                      mono
                      accent={t.status}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function statusIcon(status: ToolCallEntry["status"]) {
  if (status === "calling") {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-jade-light" />;
  }
  if (status === "error") {
    return <XCircle className="h-3.5 w-3.5 text-cinnabar" />;
  }
  return <CheckCircle2 className="h-3.5 w-3.5 text-jade" />;
}

function summarizeArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "()";
  return entries
    .slice(0, 2)
    .map(([k, v]) => {
      const s = typeof v === "string" ? v : JSON.stringify(v);
      return `${k}=${s.length > 16 ? s.slice(0, 16) + "…" : s}`;
    })
    .join("  ");
}

function KV({
  label,
  value,
  mono,
  accent,
}: {
  label: string;
  value: unknown;
  mono?: boolean;
  accent?: ToolCallEntry["status"];
}) {
  const text =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-widest text-ink-soft">
        {label}
      </div>
      <pre
        className={cn(
          "overflow-x-auto rounded border border-silk bg-paper/80 p-2 text-xs leading-relaxed",
          mono && "font-mono",
          accent === "error" && "border-cinnabar/30 text-cinnabar",
          accent === "ok" && "text-jade",
        )}
      >
        {text}
      </pre>
    </div>
  );
}
