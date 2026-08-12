import { type ClassValue, clsx } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

export function shortId(id: string, head = 6, tail = 4): string {
  if (!id) return "";
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

/** 解析工具全限定名 "<server>:<name>" -> {server, name} */
export function parseQualifiedName(qualified: string): { server: string; name: string } {
  const idx = qualified.indexOf(":");
  if (idx < 0) return { server: "default", name: qualified };
  return { server: qualified.slice(0, idx), name: qualified.slice(idx + 1) };
}

/** JSON 校验（try-parse） */
export function tryParseJson(text: string): { ok: true; value: unknown } | { ok: false; error: string } {
  if (!text.trim()) return { ok: false, error: "空字符串" };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
}

/** 从 JSON 中提取简短的 game_state 概览 */
export function summarizeGameState(value: unknown): {
  variant: string;
  round: string;
  players: number;
  tilesRemaining: number | null;
} {
  if (!value || typeof value !== "object") {
    return { variant: "—", round: "—", players: 0, tilesRemaining: null };
  }
  const v = value as Record<string, unknown>;
  const variant = typeof v.variant === "string" ? v.variant : "标准四人";
  const round = typeof v.round === "string" ? v.round : "东一局 0 本场";
  const players = Array.isArray(v.players) ? v.players.length : 0;
  const tilesRemaining = typeof v.tiles_remaining === "number" ? v.tiles_remaining : null;
  return { variant, round, players, tilesRemaining };
}

/** UUID v4 轻量版（不依赖 crypto） */
export function uuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
