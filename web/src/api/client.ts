import { consumeSseBuffer, formatApiError, parseJson, parseSseEvent, requestJson } from "./http";
import type {
  HealthResponse,
  UiConfigResponse,
  UiConfigUpdateResponse,
  ConfigSummary,
  DoctorStatus,
  DoctorCheck,
  DoctorReport,
  ConfigDiagnosticItem,
  ConfigDiagnostics,
  SourceConnectorCatalogItem,
  SourceCatalogResponse,
  ConfigFormProvider,
  ConfigImageProvider,
  ModelCapabilitySuggestion,
  ModelProviderSummary,
  ModelProvidersResponse,
  ModelDiscoveryResponse,
  ModelApplyCapabilitiesResponse,
  ModelProviderProbeState,
  ConfigVaultProfile,
  ConfigVaultSummary,
  VaultProfile,
  VaultListResponse,
  VaultSelector,
  ConfigForm,
  UiStatusResponse,
  GraphNode,
  GraphEdge,
  GraphResponse,
  QueryResult,
  QueryGapSuggestion,
  QueryTrendResponse,
  ChatMessageItem,
  ChatCitation,
  ChatToolTraceItem,
  ChatEvent,
  ChatRunLink,
  ChatTurnRecord,
  ChatResponse,
  ChatStreamEvent,
  ChatSessionSummary,
  ChatIngestCandidate,
  ChatSessionRecord,
  ChatSessionListResponse,
  ChatSessionDeleteResponse,
  WorkflowResponse,
  ChatSessionWorkflowResponse,
  PageSummary,
  PageDetail,
  PageRelation,
  ReportSummary,
  ReportDetail,
  TokenMetricGroup,
  TokenPayloadFieldGroup,
  TokenCallRecord,
  TokenAnalysis
} from "./types";

export type {
  HealthResponse,
  UiConfigResponse,
  UiConfigUpdateResponse,
  ConfigSummary,
  DoctorStatus,
  DoctorCheck,
  DoctorReport,
  ConfigDiagnosticItem,
  ConfigDiagnostics,
  SourceConnectorCatalogItem,
  SourceCatalogResponse,
  ConfigFormProvider,
  ConfigImageProvider,
  ModelCapabilitySuggestion,
  ModelProviderSummary,
  ModelProvidersResponse,
  ModelDiscoveryResponse,
  ModelApplyCapabilitiesResponse,
  ModelProviderProbeState,
  ConfigVaultProfile,
  ConfigVaultSummary,
  VaultProfile,
  VaultListResponse,
  VaultSelector,
  ConfigForm,
  UiStatusResponse,
  GraphNode,
  GraphEdge,
  GraphResponse,
  QueryResult,
  QueryGapSuggestion,
  QueryTrendResponse,
  ChatMessageItem,
  ChatCitation,
  ChatToolTraceItem,
  ChatEvent,
  ChatRunLink,
  ChatTurnRecord,
  ChatResponse,
  ChatStreamEvent,
  ChatSessionSummary,
  ChatIngestCandidate,
  ChatSessionRecord,
  ChatSessionListResponse,
  ChatSessionDeleteResponse,
  WorkflowResponse,
  ChatSessionWorkflowResponse,
  PageSummary,
  PageDetail,
  PageRelation,
  ReportSummary,
  ReportDetail,
  TokenMetricGroup,
  TokenPayloadFieldGroup,
  TokenCallRecord,
  TokenAnalysis
} from "./types";

export async function getHealth(): Promise<HealthResponse> {
  return requestJson("/health");
}

export async function getDoctor(
  configPath?: string | null,
  options: { checkModelRuntime?: boolean; checkConnectorRuntime?: boolean } = {},
): Promise<DoctorReport> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  if (options.checkModelRuntime === false) params.set("check_model_runtime", "false");
  if (options.checkConnectorRuntime === false) params.set("check_connector_runtime", "false");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/doctor${suffix}`);
}

export async function getConfig(): Promise<UiConfigResponse> {
  return requestJson("/ui/api/config");
}

export async function getVaults(configPath?: string | null): Promise<VaultListResponse> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/vaults${suffix}`);
}

export async function saveConfig(configPath: string | null, content: string): Promise<UiConfigUpdateResponse> {
  return requestJson("/ui/api/config", {
    method: "PUT",
    body: { config_path: configPath, content },
  });
}

export async function getConfigForm(configPath?: string | null): Promise<ConfigForm> {
  const suffix = configPath ? `?config_path=${encodeURIComponent(configPath)}` : "";
  return requestJson(`/ui/api/config/form${suffix}`);
}

export async function getModelProviders(configPath?: string | null): Promise<ModelProvidersResponse> {
  const suffix = configPath ? `?config_path=${encodeURIComponent(configPath)}` : "";
  return requestJson(`/models/providers${suffix}`);
}

export async function getConfigDiagnostics(configPath?: string | null, options: { refreshSourceCounts?: boolean } = {}): Promise<ConfigDiagnostics> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  if (options.refreshSourceCounts) params.set("refresh_source_counts", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/ui/api/config/diagnostics${suffix}`);
}

export async function getSourceCatalog(configPath?: string | null, connectors: string[] = []): Promise<SourceCatalogResponse> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  for (const connector of connectors) params.append("connector", connector);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/sources${suffix}`);
}

export async function saveConfigForm(configPath: string | null, form: ConfigForm): Promise<UiConfigUpdateResponse> {
  const { diagnostics: _diagnostics, ...payload } = sanitizeConfigForm(form);
  return requestJson("/ui/api/config/form", {
    method: "PUT",
    body: { ...payload, config_path: configPath },
  });
}

function sanitizeConfigForm(form: ConfigForm): ConfigForm {
  return {
    ...form,
    providers: form.providers.map(({ api_key_value: _apiKeyValue, ...provider }) => provider),
    image_providers: form.image_providers.map(({ api_key_value: _apiKeyValue, ...provider }) => provider),
  };
}

export async function discoverModelProvider(configPath: string | null, provider: string): Promise<ModelDiscoveryResponse> {
  return requestJson("/models/discover", {
    method: "POST",
    body: { config_path: configPath, provider },
  });
}

export async function applyModelCapabilities(
  configPath: string | null,
  provider: string,
  values: ModelCapabilitySuggestion,
): Promise<ModelApplyCapabilitiesResponse> {
  return requestJson("/models/apply-capabilities", {
    method: "POST",
    body: {
      config_path: configPath,
      provider,
      context_window: values.context_window ?? null,
      max_output_tokens: values.max_output_tokens ?? null,
      json_mode: values.json_mode ?? null,
    },
  });
}

export async function getStatus(vaultPath: string): Promise<UiStatusResponse> {
  return requestJson(`/ui/api/status?vault_path=${encodeURIComponent(vaultPath)}`);
}

export async function getGraph(vaultPath: string, view: "page" = "page"): Promise<GraphResponse> {
  return requestJson(`/ui/api/graph?vault_path=${encodeURIComponent(vaultPath)}&view=${encodeURIComponent(view)}`);
}

export async function getPages(selector: VaultSelector): Promise<{ vault_path: string; pages: PageSummary[] }> {
  return requestJson(`/wiki/pages?${singleVaultQuery(selector)}`);
}

export async function getPage(selector: VaultSelector, path: string): Promise<PageDetail> {
  return requestJson(`/wiki/pages/content?${singleVaultQuery(selector)}&path=${encodeURIComponent(path)}`);
}

export async function getPageRelations(selector: VaultSelector, path: string): Promise<{ path: string; outgoing_pages: PageRelation[]; incoming_pages: PageRelation[] }> {
  return requestJson(`/wiki/pages/relations?${singleVaultQuery(selector)}&path=${encodeURIComponent(path)}`);
}

export async function updatePage(selector: VaultSelector, path: string, content: string): Promise<PageDetail> {
  return requestJson("/wiki/pages/content", {
    method: "PATCH",
    body: { path, content, ...selectorToBody(selector) },
  });
}

export type PageDeleteResponse = {
  deleted: boolean;
  path: string;
  archived_path: string;
};

export async function deletePage(selector: VaultSelector, path: string): Promise<PageDeleteResponse> {
  return requestJson("/wiki/pages/content", {
    method: "DELETE",
    body: { path, ...selectorToBody(selector) },
  });
}

function selectorToBody(selector: VaultSelector): Record<string, unknown> {
  return {
    config_path: selector.config_path ?? undefined,
    vault_id: selector.vault_id ?? undefined,
    vault_path: selector.vault_id ? undefined : selector.vault_path ?? undefined,
  };
}

export type VaultScopedListOptions = {
  config_path?: string | null;
  vault_id?: string | null;
  vault_ids?: string[];
  all_vaults?: boolean;
};

function singleVaultQuery(selector: VaultSelector) {
  const params = new URLSearchParams();
  if (selector.config_path) params.set("config_path", selector.config_path);
  if (selector.vault_id) params.set("vault_id", selector.vault_id);
  if (!selector.vault_id && selector.vault_path) params.set("vault_path", selector.vault_path);
  return params.toString();
}

function vaultListQuery(selector: VaultSelector, options: VaultScopedListOptions = {}) {
  const params = new URLSearchParams();
  const configPath = options.config_path ?? selector.config_path;
  if (configPath) params.set("config_path", configPath);
  if (options.vault_id) {
    params.set("vault_id", options.vault_id);
  } else if (selector.vault_id && !options.all_vaults && !options.vault_ids?.length) {
    params.set("vault_id", selector.vault_id);
  } else if (!options.all_vaults && !options.vault_ids?.length && selector.vault_path) {
    params.set("vault_path", selector.vault_path);
  }
  if (options.all_vaults) params.set("all_vaults", "true");
  for (const vaultId of options.vault_ids || []) params.append("vault_ids", vaultId);
  return params.toString();
}

export async function getReports(selector: VaultSelector, options: VaultScopedListOptions = {}): Promise<{ vault_path: string; vault_id?: string | null; vault_name?: string | null; reports: ReportSummary[] }> {
  return requestJson(`/reports?${vaultListQuery(selector, options)}`);
}

export async function getReport(selector: VaultSelector, path: string): Promise<ReportDetail> {
  return requestJson(`/reports/content?${singleVaultQuery(selector)}&path=${encodeURIComponent(path)}`);
}

export async function getTokenAnalysis(vaultPath: string, limit = 5000): Promise<TokenAnalysis> {
  return requestJson(`/ui/api/tokens?vault_path=${encodeURIComponent(vaultPath)}&limit=${limit}`);
}

export async function runIngest(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/ingest", { method: "POST", body: { execution: "queued", kind: "connectors", ...body } });
}

export async function runIngestFile(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/ingest", { method: "POST", body: { execution: "queued", kind: "file", ...body } });
}

export async function runIngestFolder(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/ingest", { method: "POST", body: { execution: "queued", kind: "folder", ...body } });
}

export async function ingestExcerpt(
  selector: VaultSelector,
  body: {
    excerpt_text: string;
    excerpt_title?: string;
    excerpt_context?: Record<string, unknown>;
  },
): Promise<WorkflowResponse> {
  return requestJson("/ingest", {
    method: "POST",
    body: {
      execution: "queued",
      kind: "excerpt",
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      write: true,
      write_report: true,
      append_ledger: true,
      auto_scoped_lint: true,
      auto_apply_safe_lint_fixes: true,
      ...body,
    },
  });
}

export async function runLint(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/lint", { method: "POST", body: { execution: "queued", ...body } });
}

export async function getRuns(selector: VaultSelector, activeOnly = false, limit = 50, options: VaultScopedListOptions = {}): Promise<{ runs: import("../types").RunRecord[] }> {
  const params = vaultListQuery(selector, options);
  return requestJson(`/runs?${params}&active_only=${activeOnly ? "true" : "false"}&limit=${limit}`);
}

export async function getActiveRuns(selector: VaultSelector): Promise<{ runs: import("../types").RunRecord[] }> {
  return requestJson(`/runs?${singleVaultQuery(selector)}&active_only=true`);
}

export async function getRunEvents(selector: VaultSelector, runId: string, after = 0): Promise<{ events: import("../types").RunEvent[] }> {
  return requestJson(`/runs/${encodeURIComponent(runId)}/events?${singleVaultQuery(selector)}&after=${after}`);
}

export async function cancelRun(selector: VaultSelector, runId: string): Promise<import("../types").RunRecord> {
  return requestJson(`/runs/${encodeURIComponent(runId)}/cancel?${singleVaultQuery(selector)}`, { method: "POST" });
}

export async function rerunFailedRun(selector: VaultSelector, runId: string, body: Record<string, unknown> = {}): Promise<unknown> {
  return requestJson("/ingest", {
    method: "POST",
    body: { execution: "queued", kind: "recovery", config_path: selector.config_path, vault_id: selector.vault_id, recovery_vault_path: selector.vault_path, recovery_of_run_id: runId, ...body },
  });
}

export type QuerySearchOptions = {
  mode?: "quick" | "balanced" | "deep";
  page_dirs?: string[];
  max_results?: number;
  max_context_chars?: number;
  vault_ids?: string[];
  all_vaults?: boolean;
  include_content?: boolean;
};

export async function searchWiki(
  selector: VaultSelector,
  query: string,
  options: QuerySearchOptions = {},
): Promise<{
  results: QueryResult[];
  primary_pages?: QueryResult[];
  supporting_pages?: QueryResult[];
  source_pages?: QueryResult[];
  context_pack: string;
  response_guidance: string[];
  gap_suggestions: QueryGapSuggestion[];
  gaps: string[];
  warnings: string[];
  trace?: Record<string, unknown>;
}> {
  return requestJson("/query", {
    method: "POST",
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      query,
      vault_ids: options.vault_ids || [],
      all_vaults: options.all_vaults || false,
      mode: options.mode || "balanced",
      page_dirs: options.page_dirs || [],
      max_results: options.max_results || 6,
      max_context_chars: options.max_context_chars || 200000,
      include_content: options.include_content ?? true,
    },
  });
}

export async function sendChatMessage(
  selector: VaultSelector,
  messages: ChatMessageItem[],
  options: {
    vault_ids?: string[];
    all_vaults?: boolean;
    max_turns?: number;
    session_id?: string | null;
    provider?: string | null;
  } = {},
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return requestJson("/chat", {
    method: "POST",
    signal,
    body: {
      schema_version: "chat_request.v1",
      session_id: options.session_id || undefined,
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      vault_ids: options.vault_ids || [],
      all_vaults: options.all_vaults || false,
      messages,
      max_turns: options.max_turns || 6,
      include_trace: true,
      provider: options.provider || undefined,
    },
  });
}

export async function sendChatMessageStream(
  selector: VaultSelector,
  messages: ChatMessageItem[],
  options: {
    vault_ids?: string[];
    all_vaults?: boolean;
    max_turns?: number;
    session_id?: string | null;
    provider?: string | null;
  } = {},
  onEvent?: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const body = {
    schema_version: "chat_request.v1",
    session_id: options.session_id || undefined,
    config_path: selector.config_path,
    vault_id: selector.vault_id,
    vault_path: selector.vault_id ? undefined : selector.vault_path,
    vault_ids: options.vault_ids || [],
    all_vaults: options.all_vaults || false,
    messages,
    max_turns: options.max_turns || 6,
    include_trace: true,
    provider: options.provider || undefined,
  };
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatApiError(parseJson(text), text));
  }
  if (!response.body) {
    return sendChatMessage(selector, messages, options, signal);
  }

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
        throw new Error(typeof event.message === "string" && event.message ? event.message : "Chat stream failed.");
      }
      if (event.event === "final" && event.response) {
        finalResponse = event.response;
      }
    }
  }
  if (buffer.trim()) {
    for (const event of parseSseEvent(buffer)) {
      onEvent?.(event);
      if (event.event === "final" && event.response) finalResponse = event.response;
    }
  }
  if (!finalResponse) {
    throw new Error("Chat stream ended without a final response.");
  }
  return finalResponse;
}

export async function listChatSessions(selector: VaultSelector, limit = 12): Promise<ChatSessionListResponse> {
  const params = new URLSearchParams();
  if (selector.config_path) params.set("config_path", selector.config_path);
  if (selector.vault_id) params.set("vault_id", selector.vault_id);
  if (!selector.vault_id && selector.vault_path) params.set("vault_path", selector.vault_path);
  params.set("limit", String(limit));
  return requestJson(`/chat/sessions?${params.toString()}`);
}

export async function readChatSession(selector: VaultSelector, sessionId: string): Promise<ChatSessionRecord> {
  const params = new URLSearchParams();
  if (selector.config_path) params.set("config_path", selector.config_path);
  if (selector.vault_id) params.set("vault_id", selector.vault_id);
  if (!selector.vault_id && selector.vault_path) params.set("vault_path", selector.vault_path);
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}?${params.toString()}`);
}

export async function deleteChatSession(selector: VaultSelector, sessionId: string): Promise<ChatSessionDeleteResponse> {
  const params = new URLSearchParams();
  if (selector.config_path) params.set("config_path", selector.config_path);
  if (selector.vault_id) params.set("vault_id", selector.vault_id);
  if (!selector.vault_id && selector.vault_path) params.set("vault_path", selector.vault_path);
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}?${params.toString()}`, { method: "DELETE" });
}

export async function updateChatSession(selector: VaultSelector, sessionId: string, title: string): Promise<ChatSessionRecord> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      title,
    },
  });
}

export async function ingestChatSession(
  selector: VaultSelector,
  sessionId: string,
  opts: { turn_indices?: number[] } = {},
): Promise<WorkflowResponse> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/ingest`, {
    method: "POST",
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      write: true,
      write_report: true,
      append_ledger: true,
      auto_scoped_lint: true,
      auto_apply_safe_lint_fixes: true,
      turn_indices: opts.turn_indices ?? null,
    },
  });
}

export async function retryChatSession(
  selector: VaultSelector,
  sessionId: string,
  options: {
    all_vaults?: boolean;
    max_turns?: number;
    provider?: string | null;
  } = {},
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/retry`, {
    method: "POST",
    signal,
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      all_vaults: options.all_vaults || false,
      max_turns: options.max_turns || 6,
      include_trace: true,
      provider: options.provider || undefined,
    },
  });
}

export async function deleteChatTurn(selector: VaultSelector, sessionId: string, turnIndex: number): Promise<ChatSessionRecord> {
  const params = new URLSearchParams();
  if (selector.config_path) params.set("config_path", selector.config_path);
  if (selector.vault_id) params.set("vault_id", selector.vault_id);
  if (!selector.vault_id && selector.vault_path) params.set("vault_path", selector.vault_path);
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnIndex)}?${params.toString()}`, { method: "DELETE" });
}

export async function closeChatSession(selector: VaultSelector, sessionId: string): Promise<ChatSessionWorkflowResponse> {
  return requestJson(`/chat/sessions/${encodeURIComponent(sessionId)}/close`, {
    method: "POST",
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      write: true,
      write_report: true,
      append_ledger: true,
    },
  });
}

export async function sendQueryFeedback(
  selector: VaultSelector,
  body: {
    query: string;
    useful?: boolean | null;
    selected_paths?: string[];
    rejected_paths?: string[];
    comment?: string;
  },
): Promise<{ recorded: boolean; ledger_path: string }> {
  return requestJson("/query/feedback", {
    method: "POST",
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      query: body.query,
      useful: body.useful ?? null,
      selected_paths: body.selected_paths || [],
      rejected_paths: body.rejected_paths || [],
      comment: body.comment || "",
      caller: "web",
    },
  });
}

export async function getQueryTrends(selector: VaultSelector, limit = 100): Promise<QueryTrendResponse> {
  return requestJson(`/query/trends?${singleVaultQuery(selector)}&limit=${limit}`);
}
