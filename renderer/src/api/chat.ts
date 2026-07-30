import { consumeSseBuffer, openEventStream, parseSseEvent, requestJson } from "./http";
import { selectorToBody, singleVaultQuery } from "./scope";
import type {
  ChatCitation,
  ChatCitationResolveResponse,
  ChatMessageItem,
  ChatResponse,
  ChatSessionDeleteResponse,
  ChatSessionListResponse,
  ChatSessionRecord,
  ChatSessionSummary,
  ChatSessionWorkflowResponse,
  ChatStreamEvent,
  VaultSelector,
  WorkflowResponse,
} from "./types";

export type ChatRequestOptions = {
  vault_ids?: string[];
  all_vaults?: boolean;
  session_id?: string | null;
  expected_session_revision?: number | null;
  provider?: string | null;
};

export class ChatStreamError extends Error {
  readonly code: string;
  readonly category: string;
  readonly retryable: boolean;
  readonly stage: string;

  constructor(event: ChatStreamEvent) {
    const details = event.error || {};
    const message = typeof details.message === "string" && details.message
      ? details.message
      : typeof event.message === "string" && event.message
        ? event.message
        : "Chat stream failed.";
    super(message);
    this.name = "ChatStreamError";
    this.code = typeof details.code === "string" ? details.code : "KA-CHAT-STREAM";
    this.category = typeof details.category === "string" ? details.category : "internal_error";
    this.retryable = details.retryable === true;
    this.stage = typeof details.stage === "string" ? details.stage : "running";
  }
}

function chatRequestBody(selector: VaultSelector, messages: ChatMessageItem[], options: ChatRequestOptions) {
  const message = [...messages].reverse().find((item) => item.role === "user");
  if (!message) throw new Error("Chat request requires a user message.");
  return {
    schema_version: "chat_request.v4",
    request_id: `req_${crypto.randomUUID().replace(/-/g, "")}`,
    execution_id: `exec_${crypto.randomUUID().replace(/-/g, "")}`,
    session_id: options.session_id || undefined,
    expected_session_revision: options.expected_session_revision || undefined,
    ...selectorToBody(selector),
    vault_ids: options.vault_ids || [],
    all_vaults: options.all_vaults || false,
    message: { ...message, message_id: message.message_id || `msg_${crypto.randomUUID().replace(/-/g, "")}` },
    include_trace: true,
    provider: options.provider || undefined,
  };
}

export async function sendChatMessage(
  selector: VaultSelector,
  messages: ChatMessageItem[],
  options: ChatRequestOptions = {},
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return requestJson("/chat", {
    method: "POST",
    signal,
    body: chatRequestBody(selector, messages, options),
  });
}

export async function resolveChatCitations(
  selector: VaultSelector,
  citations: ChatCitation[],
): Promise<ChatCitationResolveResponse> {
  return requestJson("/chat/citations/resolve", {
    method: "POST",
    body: {
      schema_version: "chat_citation_resolve_request.v1",
      ...selectorToBody(selector),
      citations,
    },
  });
}

export async function sendChatMessageStream(
  selector: VaultSelector,
  messages: ChatMessageItem[],
  options: ChatRequestOptions = {},
  onEvent?: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await openEventStream("/chat/stream", chatRequestBody(selector, messages, options), signal);
  if (!response.body) return sendChatMessage(selector, messages, options, signal);

  let finalResponse: ChatResponse | null = null;
  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = consumeSseBuffer(buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      onEvent?.(event);
      if (event.event === "error") {
        throw new ChatStreamError(event);
      }
      if (event.event === "final" && event.response) finalResponse = event.response;
    }
  }
  if (buffer.trim()) {
    for (const event of parseSseEvent(buffer)) {
      onEvent?.(event);
      if (event.event === "error") throw new ChatStreamError(event);
      if (event.event === "final" && event.response) finalResponse = event.response;
    }
  }
  if (!finalResponse) throw new Error("Chat stream ended without a final response.");
  return finalResponse;
}

export async function listChatSessions(
  selector: VaultSelector,
  limit = 12,
  offset = 0,
): Promise<ChatSessionListResponse> {
  return requestJson(
    `/chat/sessions?${singleVaultQuery(selector)}&limit=${limit}&offset=${offset}`,
  );
}

export async function listAllChatSessions(
  selector: VaultSelector,
  pageSize = 200,
): Promise<ChatSessionListResponse> {
  const sessions: ChatSessionSummary[] = [];
  let offset = 0;
  let totalCount = 0;
  while (true) {
    const page = await listChatSessions(selector, pageSize, offset);
    sessions.push(...(page.sessions || []));
    totalCount = page.total_count ?? sessions.length;
    if (!page.has_more || !page.sessions?.length) {
      return {
        sessions,
        total_count: Math.max(totalCount, sessions.length),
        offset: 0,
        limit: pageSize,
        has_more: false,
      };
    }
    offset += page.sessions.length;
  }
}

export async function readChatSession(selector: VaultSelector, sessionId: string): Promise<ChatSessionRecord> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}?${singleVaultQuery(selector)}`);
}

export async function deleteChatSession(selector: VaultSelector, sessionId: string, expectedSessionRevision: number): Promise<ChatSessionDeleteResponse> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    body: { ...selectorToBody(selector), expected_session_revision: expectedSessionRevision },
  });
}

export async function updateChatSession(selector: VaultSelector, sessionId: string, title: string, expectedSessionRevision: number): Promise<ChatSessionRecord> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: { ...selectorToBody(selector), title, expected_session_revision: expectedSessionRevision },
  });
}

export async function ingestChatSession(
  selector: VaultSelector,
  sessionId: string,
  opts: { expected_session_revision: number; turn_ids?: string[]; source_title?: string; target_vault_id?: string; target_vault_path?: string },
): Promise<WorkflowResponse> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/ingest`, {
    method: "POST",
    body: {
      ...selectorToBody(selector),
      target_vault_id: opts.target_vault_id || undefined,
      target_vault_path: opts.target_vault_id ? undefined : opts.target_vault_path,
      write: true,
      write_report: true,
      append_ledger: true,
      auto_scoped_lint: true,
      expected_session_revision: opts.expected_session_revision,
      source_title: opts.source_title || undefined,
      turn_ids: opts.turn_ids ?? null,
    },
  });
}

export async function retryChatSession(
  selector: VaultSelector,
  sessionId: string,
  options: Omit<ChatRequestOptions, "vault_ids" | "session_id"> & { target_turn_id: string; expected_session_revision: number },
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/retry`, {
    method: "POST",
    signal,
    body: {
      ...selectorToBody(selector),
      all_vaults: options.all_vaults || false,
      include_trace: true,
      target_turn_id: options.target_turn_id,
      expected_session_revision: options.expected_session_revision,
      schema_version: "chat_session_retry_request.v4",
      provider: options.provider || undefined,
    },
  });
}

export async function deleteChatTurn(selector: VaultSelector, sessionId: string, turnId: string, expectedSessionRevision: number): Promise<ChatSessionRecord> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}`, {
    method: "DELETE",
    body: { ...selectorToBody(selector), expected_session_revision: expectedSessionRevision },
  });
}

export async function closeChatSession(selector: VaultSelector, sessionId: string, expectedSessionRevision: number): Promise<ChatSessionWorkflowResponse> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/close`, {
    method: "POST",
    body: {
      ...selectorToBody(selector),
      write: true,
      write_report: true,
      append_ledger: true,
      expected_session_revision: expectedSessionRevision,
    },
  });
}

