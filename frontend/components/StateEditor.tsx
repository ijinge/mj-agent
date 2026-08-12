"use client";

import { useEffect, useRef } from "react";
import { AlertCircle, Check } from "lucide-react";
import { cn, tryParseJson } from "@/lib/utils";

export function StateEditor({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const parsed = tryParseJson(value);

  // 简单自动缩进：Tab 插入 2 空格
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        const before = value.slice(0, start);
        const after = value.slice(end);
        const newValue = before + "  " + after;
        onChange(newValue);
        requestAnimationFrame(() => {
          ta.selectionStart = ta.selectionEnd = start + 2;
        });
      }
    };
    ta.addEventListener("keydown", handler);
    return () => ta.removeEventListener("keydown", handler);
  }, [value, onChange]);

  return (
    <div className={cn("relative", className)}>
      <div
        className={cn(
          "overflow-hidden rounded border bg-paper-deep/40 transition-colors",
          parsed.ok ? "border-silk focus-within:border-jade" : "border-cinnabar/40",
        )}
      >
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          rows={14}
          placeholder='{"variant": "...", "players": [...], ...}'
          className={cn(
            "block w-full resize-y bg-transparent px-3 py-2.5",
            "font-mono text-[12.5px] leading-relaxed text-ink",
            "placeholder:text-ink-soft/40",
            "focus:outline-none",
          )}
        />
        {/* 状态条 */}
        <div
          className={cn(
            "flex items-center justify-between border-t px-2.5 py-1.5",
            "font-mono text-[10px]",
            parsed.ok
              ? "border-silk/60 bg-paper-deep/40 text-ink-soft"
              : "border-cinnabar/20 bg-cinnabar/5 text-cinnabar",
          )}
        >
          {parsed.ok ? (
            <>
              <span className="flex items-center gap-1">
                <Check className="h-3 w-3" />
                JSON 合法
              </span>
              <span>{value.length} chars</span>
            </>
          ) : (
            <>
              <span className="flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {parsed.error}
              </span>
              <button
                type="button"
                onClick={() => {
                  try {
                    onChange(JSON.stringify(JSON.parse(value), null, 2));
                  } catch {
                    /* noop */
                  }
                }}
                className="text-ink-soft underline-offset-2 hover:text-jade hover:underline"
              >
                尝试格式化
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
