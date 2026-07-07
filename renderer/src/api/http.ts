import type { ChatStreamEvent } from "./types";

export async function requestJson<T>(url: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const init: RequestInit = {
    method: options.method || "GET",
    headers: { Accept: "application/json" },
    signal: options.signal,
  };
  if (options.body !== undefined) {
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(url, init);
  const text = await response.text();
  const data = text ? parseJson(text) : null;
  if (!response.ok) {
    throw new Error(formatApiError(data, text));
  }
  return data as T;
}

export function formatApiError(data: unknown, fallback: string): string {
  if (isRecord(data) && isRecord(data.error)) {
    const error = data.error;
    const code = typeof error.code === "string" ? error.code : "KA-UNKNOWN";
    const category = typeof error.category === "string" ? error.category : "unknown";
    const message = typeof error.message === "string" ? error.message : fallback || "Request failed.";
    const retryable = error.retryable === true ? " · retryable" : "";
    const hint = typeof error.hint === "string" && error.hint ? `\nHint: ${error.hint}` : "";
    return `[${code}] ${category}${retryable}: ${message}${hint}`;
  }
  const detail = isRecord(data) && "detail" in data ? data.detail : fallback;
  return typeof detail === "string" ? detail : JSON.stringify(detail);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function consumeSseBuffer(buffer: string): { events: ChatStreamEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const chunks = normalized.split("\n\n");
  const rest = chunks.pop() || "";
  return {
    events: chunks.flatMap((chunk) => parseSseEvent(chunk)),
    rest,
  };
}

export function parseSseEvent(chunk: string): ChatStreamEvent[] {
  const dataLines = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (!dataLines.length) return [];
  const data = dataLines.join("\n");
  const parsed = parseJson(data);
  if (!isRecord(parsed) || parsed.schema_version !== "chat_stream_event.v1") return [];
  return [parsed as ChatStreamEvent];
}
