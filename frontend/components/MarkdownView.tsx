"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

export function MarkdownView({
  content,
  streaming = false,
  className,
}: {
  content: string;
  streaming?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("prose-mj relative", className)}>
      {content ? (
        <>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          {streaming && <span className="stream-cursor" aria-hidden="true" />}
        </>
      ) : (
        <div className="flex min-h-[280px] items-center justify-center py-12 text-center">
          <p className="text-sm text-ink-soft">
            提交牌局信息后，AI 推演过程将在此流式输出。
          </p>
        </div>
      )}
    </div>
  );
}
