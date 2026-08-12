"use client";

import { useState } from "react";
import { Loader2, Send, Eraser, Eye, Code } from "lucide-react";
import { cn, tryParseJson } from "@/lib/utils";
import { StateEditor } from "./StateEditor";
import { renderGameState } from "@/lib/json2cn";

export function InputPanel({
  gameId,
  onGameIdChange,
  gameState,
  onGameStateChange,
  question,
  onQuestionChange,
  onSubmit,
  onClear,
  loading,
  className,
}: {
  gameId: string;
  onGameIdChange: (v: string) => void;
  gameState: string;
  onGameStateChange: (v: string) => void;
  question: string;
  onQuestionChange: (v: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  loading: boolean;
  className?: string;
}) {
  const [viewMode, setViewMode] = useState<"json" | "rendered">("json");
  const parsed = tryParseJson(gameState);
  const canSubmit =
    !loading &&
    gameId.trim() !== "" &&
    parsed.ok &&
    question.trim() !== "";

  // 渲染中文场面描述
  const renderedText = (() => {
    if (!parsed.ok) return "JSON 解析失败，无法渲染";
    try {
      return renderGameState(parsed.value as Record<string, any>);
    } catch (e) {
      return `渲染失败：${e instanceof Error ? e.message : String(e)}`;
    }
  })();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) onSubmit();
      }}
      className={cn(
        "flex flex-col gap-4 rounded-lg border border-silk bg-paper p-5",
        className,
      )}
    >
      {/* 地方麻将类型 ID */}
      <div>
        <label
          htmlFor="game-id"
          className="mb-1.5 block text-sm font-medium text-ink"
        >
          地方麻将类型 ID
        </label>
        <input
          id="game-id"
          type="text"
          value={gameId}
          onChange={(e) => onGameIdChange(e.target.value)}
          placeholder="例如：ncmj-server（须与 MCP server name 一致）"
          className={cn(
            "block w-full rounded border border-silk bg-paper px-3 py-2",
            "font-mono text-sm text-ink",
            "placeholder:text-ink-soft/40",
            "focus:border-jade focus:outline-none",
          )}
        />
      </div>

      {/* 用户提问 */}
      <div>
        <label
          htmlFor="question"
          className="mb-1.5 block text-sm font-medium text-ink"
        >
          用户提问
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => onQuestionChange(e.target.value)}
          rows={2}
          placeholder="例：现在该打哪张？/ 该不该吃上家二条？"
          className={cn(
            "block w-full resize-y rounded border border-silk bg-paper px-3 py-2",
            "text-sm leading-relaxed text-ink",
            "placeholder:text-ink-soft/40",
            "focus:border-jade focus:outline-none",
          )}
        />
      </div>

      {/* 场面信息 JSON */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <label
            htmlFor="game-state"
            className="block text-sm font-medium text-ink"
          >
            场面信息 {viewMode === "json" ? "(JSON)" : "(中文)"}
          </label>
          <button
            type="button"
            onClick={() => setViewMode(viewMode === "json" ? "rendered" : "json")}
            className={cn(
              "flex items-center gap-1.5 rounded px-2.5 py-1",
              "text-xs font-medium transition-colors",
              viewMode === "rendered"
                ? "bg-jade/10 text-jade hover:bg-jade/20"
                : "bg-paper-deep/50 text-ink-soft hover:bg-paper-deep hover:text-ink",
            )}
            title={viewMode === "json" ? "切换到中文视图" : "切换到 JSON 视图"}
          >
            {viewMode === "json" ? (
              <>
                <Eye className="h-3.5 w-3.5" />
                中文视图
              </>
            ) : (
              <>
                <Code className="h-3.5 w-3.5" />
                JSON 视图
              </>
            )}
          </button>
        </div>
        {viewMode === "json" ? (
          <StateEditor value={gameState} onChange={onGameStateChange} />
        ) : (
          <div className="overflow-auto rounded border border-silk bg-paper-deep/40 p-3">
            <pre className="whitespace-pre-wrap font-mono text-[12.5px] leading-relaxed text-ink">
              {renderedText}
            </pre>
          </div>
        )}
      </div>

      {/* 按钮 */}
      <div className="flex items-center justify-between gap-3 border-t border-silk pt-4">
        <button
          type="button"
          onClick={onClear}
          disabled={loading}
          className={cn(
            "flex items-center gap-1.5 rounded px-3 py-2",
            "text-sm text-ink-soft",
            "transition-colors hover:bg-paper-deep/50 hover:text-ink",
            "disabled:opacity-50",
          )}
        >
          <Eraser className="h-3.5 w-3.5" />
          清空
        </button>

        <button
          type="submit"
          disabled={!canSubmit}
          className={cn(
            "flex items-center gap-2 rounded px-5 py-2.5",
            "text-sm font-medium",
            "transition-colors",
            canSubmit
              ? "bg-jade text-paper hover:bg-jade-light"
              : "cursor-not-allowed border border-silk bg-paper-deep text-ink-soft",
          )}
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              推演中…
            </>
          ) : (
            <>
              <Send className="h-4 w-4" />
              开始分析
            </>
          )}
        </button>
      </div>
    </form>
  );
}
