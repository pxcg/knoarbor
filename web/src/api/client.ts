export type HealthResponse = {
  status: string;
};

export type UiConfigResponse = {
  config_path: string;
  exists: boolean;
  content: string;
  summary: ConfigSummary;
};

export type UiConfigUpdateResponse = {
  config_path: string;
  saved: boolean;
  summary: ConfigSummary;
};

export type ConfigSummary = {
  project_name?: string;
  vault_path?: string;
  server?: string;
  default_provider?: string;
  provider_count?: number;
  enabled_connectors?: string[];
  enabled_document_processors?: string[];
  default_max_tokens?: number;
  request_timeout_seconds?: number;
  diagnostics?: ConfigDiagnostics;
};

export type DoctorStatus = "ok" | "warning" | "error";

export type DoctorCheck = {
  name: string;
  status: DoctorStatus;
  message: string;
  details: Record<string, unknown>;
};

export type DoctorReport = {
  schema_version: "doctor_report.v1";
  status: DoctorStatus;
  config_path?: string | null;
  checks: DoctorCheck[];
  summary: Record<DoctorStatus, number>;
};

export type ConfigDiagnosticItem = {
  name: string;
  category: string;
  enabled: boolean;
  ok: boolean;
  code: string;
  path?: string | null;
  count?: number | null;
  detail?: string;
  version?: string | null;
  source_types?: string[];
  supports_checkpoint?: boolean | null;
  supports_segmentation_hint?: boolean | null;
  requires_external_service?: boolean | null;
};

export type ConfigDiagnostics = {
  connectors: ConfigDiagnosticItem[];
  processors: ConfigDiagnosticItem[];
  providers: ConfigDiagnosticItem[];
  paths: ConfigDiagnosticItem[];
};

export type ConfigFormProvider = {
  name: string;
  base_url: string;
  api_key_env: string;
  model: string;
  json_mode: boolean;
  api_key_configured: boolean;
};

export type ConfigForm = {
  project_name: string;
  vault_path: string;
  server_host: string;
  server_port: number;
  default_provider: string;
  default_max_tokens: number | null;
  request_timeout_seconds: number;
  providers: ConfigFormProvider[];
  enabled_connectors: string[];
  codex_enabled: boolean;
  codex_sessions_dir: string;
  codex_raw_output_dir: string;
  hermes_enabled: boolean;
  hermes_sessions_dir: string;
  hermes_raw_output_dir: string;
  openclaw_enabled: boolean;
  openclaw_sessions_dir: string;
  openclaw_raw_output_dir: string;
  claude_code_enabled: boolean;
  claude_code_sessions_dir: string;
  claude_code_raw_output_dir: string;
  generic_chat_enabled: boolean;
  generic_chat_roots: string[];
  generic_chat_raw_output_dir: string;
  markdown_enabled: boolean;
  markdown_roots: string[];
  markdown_raw_output_dir: string;
  mineru_enabled: boolean;
  mineru_endpoint: string;
  mineru_input_dir: string;
  mineru_output_dir: string;
  mineru_parse_method: string;
  mineru_backend: string;
  mineru_timeout_seconds: number;
  mineru_patterns: string[];
  mineru_recursive: boolean;
  mineru_return_md: boolean;
  mineru_return_middle_json: boolean;
  mineru_return_model_output: boolean;
  mineru_return_content_list: boolean;
  mineru_return_images: boolean;
  mineru_response_format_zip: boolean;
  mineru_lang_list: string;
  mineru_formula_enable: boolean;
  mineru_table_enable: boolean;
  mineru_server_url: string;
  mineru_start_page_id: number;
  mineru_end_page_id: number;
  mineru_extra_fields_json: string;
  diagnostics?: ConfigDiagnostics;
};

export type UiStatusResponse = {
  vault_path: string;
  pages: number;
  raw_sources: number;
  issues: number;
  errors: number;
  warnings: number;
  info: number;
  directories: Record<string, number>;
};

export type GraphNode = {
  id: string;
  title: string;
  type: string;
  summary: string;
  tags: string[];
  source?: string | null;
};

export type GraphEdge = {
  source: string;
  target: string;
  kind: string;
};

export type GraphResponse = {
  vault_path: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    page_count: number;
    edge_count: number;
    orphan_count: number;
    unresolved_link_count: number;
    directory_counts: Record<string, number>;
    tag_counts: Record<string, number>;
  };
};

export type QueryResult = {
  path: string;
  title: string;
  type: string;
  status: string;
  score: number;
  relevance: string;
  match_kind: "direct" | "related";
  matched_fields: string[];
  matched_terms: Record<string, string[]>;
  reason: string;
  summary: string;
  key_points: string[];
  excerpts: Array<{ path: string; page_title: string; heading: string; section: string; content: string; score: number }>;
  content?: string | null;
  source?: string | null;
  tags: string[];
  related_pages: string[];
};

export type QueryGapSuggestion = {
  kind: "no_result" | "low_confidence";
  query: string;
  reason: string;
  recommended_action: "ingest_more_sources" | "review_query_terms" | "ask_followup";
};

export type QueryTrendResponse = {
  sample_size: number;
  no_result_count: number;
  low_confidence_count: number;
  repeated_gap_queries: Array<{ query: string; count: number }>;
};

export type PageSummary = {
  path: string;
  directory: string;
  title: string;
  page_type?: string | null;
  status?: string | null;
  updated?: string | null;
  source?: string | null;
  tags: string[];
  summary: string;
  headings: string[];
};

export type PageDetail = {
  path: string;
  content: string;
  metadata: Record<string, string>;
  summary: PageSummary;
  outbound_links: PageLink[];
  backlinks: PageLink[];
};

export type PageLink = {
  source: string;
  target: string;
  target_path?: string | null;
  resolved: boolean;
};

export type ReportSummary = {
  path: string;
  title: string;
  kind: string;
  updated?: string | null;
  size: number;
  preview: string;
};

export type ReportDetail = {
  path: string;
  content: string;
  summary: ReportSummary;
};

export type ProjectDoc = {
  path: string;
  content: string;
};

export async function getHealth(): Promise<HealthResponse> {
  return requestJson("/health");
}

export async function getDoctor(configPath?: string | null): Promise<DoctorReport> {
  const suffix = configPath ? `?config_path=${encodeURIComponent(configPath)}` : "";
  return requestJson(`/doctor${suffix}`);
}

export async function getConfig(): Promise<UiConfigResponse> {
  return requestJson("/ui/api/config");
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

export async function getConfigDiagnostics(configPath?: string | null): Promise<ConfigDiagnostics> {
  const suffix = configPath ? `?config_path=${encodeURIComponent(configPath)}` : "";
  return requestJson(`/ui/api/config/diagnostics${suffix}`);
}

export async function saveConfigForm(configPath: string | null, form: ConfigForm): Promise<UiConfigUpdateResponse> {
  const { diagnostics: _diagnostics, ...payload } = form;
  return requestJson("/ui/api/config/form", {
    method: "PUT",
    body: { ...payload, config_path: configPath },
  });
}

export async function getStatus(vaultPath: string): Promise<UiStatusResponse> {
  return requestJson(`/ui/api/status?vault_path=${encodeURIComponent(vaultPath)}`);
}

export async function getGraph(vaultPath: string): Promise<GraphResponse> {
  return requestJson(`/ui/api/graph?vault_path=${encodeURIComponent(vaultPath)}`);
}

export async function getPages(vaultPath: string): Promise<{ vault_path: string; pages: PageSummary[] }> {
  return requestJson(`/wiki/pages?vault_path=${encodeURIComponent(vaultPath)}`);
}

export async function getPage(vaultPath: string, path: string): Promise<PageDetail> {
  return requestJson(`/wiki/page?vault_path=${encodeURIComponent(vaultPath)}&path=${encodeURIComponent(path)}`);
}

export async function getPageLinks(vaultPath: string, path: string): Promise<{ path: string; outbound_links: PageLink[]; backlinks: PageLink[] }> {
  return requestJson(`/wiki/backlinks?vault_path=${encodeURIComponent(vaultPath)}&path=${encodeURIComponent(path)}`);
}

export async function getReports(vaultPath: string): Promise<{ vault_path: string; reports: ReportSummary[] }> {
  return requestJson(`/ui/api/reports?vault_path=${encodeURIComponent(vaultPath)}`);
}

export async function getReport(vaultPath: string, path: string): Promise<ReportDetail> {
  return requestJson(`/ui/api/report?vault_path=${encodeURIComponent(vaultPath)}&path=${encodeURIComponent(path)}`);
}

export async function getProjectDoc(path: string): Promise<ProjectDoc> {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  return requestJson(`/ui/api/docs/${safePath}`);
}

export async function runIngest(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/runs", { method: "POST", body: { flow: "ingest", ingest: { kind: "connectors", ...body } } });
}

export async function runIngestFile(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/runs", { method: "POST", body: { flow: "ingest", ingest: { kind: "file", ...body } } });
}

export async function runLint(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/runs", { method: "POST", body: { flow: "lint", lint: body } });
}

export async function getRuns(vaultPath: string, activeOnly = false): Promise<{ runs: import("../types").RunRecord[] }> {
  return requestJson(`/runs?vault_path=${encodeURIComponent(vaultPath)}&active_only=${activeOnly ? "true" : "false"}`);
}

export async function getActiveRuns(vaultPath: string): Promise<{ runs: import("../types").RunRecord[] }> {
  return requestJson(`/runs?vault_path=${encodeURIComponent(vaultPath)}&active_only=true`);
}

export async function getRunEvents(vaultPath: string, runId: string, after = 0): Promise<{ events: import("../types").RunEvent[] }> {
  return requestJson(`/runs/${encodeURIComponent(runId)}/events?vault_path=${encodeURIComponent(vaultPath)}&after=${after}`);
}

export async function cancelRun(vaultPath: string, runId: string): Promise<import("../types").RunRecord> {
  return requestJson(`/runs/${encodeURIComponent(runId)}/cancel?vault_path=${encodeURIComponent(vaultPath)}`, { method: "POST" });
}

export async function rerunFailedRun(vaultPath: string, runId: string, body: Record<string, unknown> = {}): Promise<unknown> {
  return requestJson("/runs", {
    method: "POST",
    body: { flow: "ingest", vault_path: vaultPath, recovery_of_run_id: runId, recovery: body },
  });
}

export type QuerySearchOptions = {
  mode?: "quick" | "balanced" | "deep";
  context_format?: "compact" | "full";
  page_dirs?: string[];
  max_results?: number;
  include_content?: boolean;
};

export async function searchWiki(
  vaultPath: string,
  query: string,
  options: QuerySearchOptions = {},
): Promise<{
  results: QueryResult[];
  context_pack: string;
  answer_guidance: string[];
  gap_suggestions: QueryGapSuggestion[];
  gaps: string[];
  warnings: string[];
  trace?: Record<string, unknown>;
}> {
  return requestJson("/query/search", {
    method: "POST",
    body: {
      obsidian_vault_path: vaultPath,
      query,
      mode: options.mode || "balanced",
      context_format: options.context_format || "compact",
      page_dirs: options.page_dirs || [],
      max_results: options.max_results || 6,
      include_content: options.include_content || false,
    },
  });
}

export async function sendQueryFeedback(
  vaultPath: string,
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
      obsidian_vault_path: vaultPath,
      query: body.query,
      useful: body.useful ?? null,
      selected_paths: body.selected_paths || [],
      rejected_paths: body.rejected_paths || [],
      comment: body.comment || "",
      caller: "web",
    },
  });
}

export async function getQueryTrends(vaultPath: string, limit = 100): Promise<QueryTrendResponse> {
  return requestJson(`/query/trends?obsidian_vault_path=${encodeURIComponent(vaultPath)}&limit=${limit}`);
}

async function requestJson<T>(url: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const init: RequestInit = {
    method: options.method || "GET",
    headers: { Accept: "application/json" },
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

function formatApiError(data: unknown, fallback: string): string {
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

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
