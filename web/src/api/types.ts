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
  vault_id?: string;
  vault_name?: string;
  vaults?: ConfigVaultSummary[];
  server?: string;
  default_provider?: string;
  provider_count?: number;
  image_default_provider?: string;
  image_provider_count?: number;
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
  next_steps: string[];
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

export type SourceConnectorCatalogItem = {
  schema_version: "source_connector_catalog_item.v1";
  name: string;
  version: string;
  source_types: string[];
  settings_schema: Record<string, unknown>;
  supports_discovery: boolean;
  supports_checkpoint: boolean;
  supports_segmentation_hint: boolean;
  requires_external_service: boolean;
  configured: boolean;
  enabled: boolean;
};

export type SourceCatalogResponse = {
  schema_version: "source_catalog.v1";
  config_path?: string | null;
  connectors: SourceConnectorCatalogItem[];
};

export type ConfigFormProvider = {
  name: string;
  adapter: "openai_compatible" | "ollama";
  base_url: string;
  api_key_env: string;
  api_key_value?: string;
  model: string;
  json_mode: boolean;
  verify_tls: boolean;
  tls_ca_file: string;
  context_window?: number | null;
  max_output_tokens?: number | null;
  extra_body?: Record<string, unknown>;
  api_key_configured: boolean;
};

export type ConfigImageProvider = {
  name: string;
  adapter: "sensenova_image";
  base_url: string;
  endpoint_path: string;
  api_key_env: string;
  api_key_value?: string;
  model: string;
  verify_tls: boolean;
  tls_ca_file: string;
  response_format: "url" | "b64_json" | string;
  size: string;
  aspect_ratio: string;
  image_count: number;
  extra_body?: Record<string, unknown>;
  api_key_configured: boolean;
};

export type ModelCapabilitySuggestion = {
  context_window?: number | null;
  max_output_tokens?: number | null;
  json_mode?: boolean | null;
};

export type ModelProviderSummary = {
  name: string;
  adapter: string;
  base_url?: string | null;
  model?: string | null;
  json_mode: boolean;
  api_key_env?: string | null;
  api_key_configured: boolean;
  verify_tls: boolean;
  tls_ca_file?: string | null;
  local_or_private: boolean;
  context_window?: number | null;
  max_output_tokens?: number | null;
  default: boolean;
};

export type ModelProvidersResponse = {
  schema_version: "model_providers.v1";
  default_provider?: string | null;
  providers: ModelProviderSummary[];
};

export type ModelDiscoveryResponse = {
  schema_version: "model_discovery.v1";
  provider: string;
  model: string;
  status: "ok" | "warning" | "error";
  available: boolean;
  message: string;
  model_ids: string[];
  model_count: number;
  configured_model_found?: boolean | null;
  detected_context_window?: number | null;
  configured_context_window?: number | null;
  effective_context_window?: number | null;
  context_window_source: string;
  configured_max_output_tokens?: number | null;
  suggested_config: ModelCapabilitySuggestion;
  details: Record<string, unknown>;
};

export type ModelProbeResponse = {
  schema_version: "model_probe.v1";
  provider: string;
  model: string;
  level: "minimal" | "structured";
  status: "ok" | "warning" | "error";
  available: boolean;
  message: string;
  latency_ms?: number | null;
  output_valid?: boolean | null;
  structured_output?: boolean | null;
  detected_context_window?: number | null;
  configured_context_window?: number | null;
  effective_context_window?: number | null;
  configured_max_output_tokens?: number | null;
  suggested_config: ModelCapabilitySuggestion;
  usage: Record<string, number>;
  details: Record<string, unknown>;
};

export type ModelApplyCapabilitiesResponse = {
  schema_version: "model_apply_capabilities.v1";
  provider: string;
  config_path: string;
  saved: boolean;
  applied: Record<string, unknown>;
};

export type ModelProviderProbeState = {
  discovery?: ModelDiscoveryResponse;
  probe?: ModelProbeResponse;
  lastAction?: "discover" | "minimal" | "structured";
};

export type ConfigVaultProfile = {
  id: string;
  name: string;
  path: string;
  active: boolean;
};

export type ConfigVaultSummary = {
  id: string;
  name: string;
  path: string;
};

export type VaultProfile = {
  id: string;
  name: string;
  path: string;
  active: boolean;
  exists: boolean;
};

export type VaultListResponse = {
  schema_version: "vaults.v1";
  config_path?: string | null;
  default_vault_id?: string | null;
  vaults: VaultProfile[];
};

export type VaultSelector = {
  config_path?: string | null;
  vault_id?: string | null;
  vault_path?: string | null;
};

export type ConfigForm = {
  project_name: string;
  vault_path: string;
  vault_id: string;
  vaults: ConfigVaultProfile[];
  server_host: string;
  server_port: number;
  default_provider: string;
  default_max_tokens: number | null;
  request_timeout_seconds: number;
  providers: ConfigFormProvider[];
  image_default_provider: string;
  image_request_timeout_seconds: number;
  image_providers: ConfigImageProvider[];
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
  role?: string | null;
  summary: string;
  entities: string[];
  pages?: string[];
  source?: string | null;
};

export type GraphEdge = {
  source: string;
  target: string;
  kind: string;
  label?: string | null;
  page?: string | null;
  claim?: string | null;
};

export type GraphView = "entity" | "page";

export type GraphResponse = {
  vault_path: string;
  graph_kind?: GraphView;
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    page_count: number;
    edge_count: number;
    orphan_count: number;
    unresolved_link_count: number;
    directory_counts: Record<string, number>;
    role_counts: Record<string, number>;
    entity_counts: Record<string, number>;
  };
};

export type QueryResult = {
  path: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  role?: "primary" | "supporting" | "source";
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
  claims: string[];
  excerpts: Array<{ path: string; page_title: string; heading: string; section: string; content: string; score: number }>;
  content?: string | null;
  source?: string | null;
  entities: string[];
  outbound_links: string[];
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

export type ChatMessageItem = {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name?: string | null;
};

export type ChatCitation = {
  kind: "page" | "report" | "run" | "source";
  role?: "primary" | "supporting" | "source" | "further_reading" | null;
  path?: string | null;
  title?: string | null;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  run_id?: string | null;
  reason?: string;
};

export type ChatToolTraceItem = {
  tool: string;
  arguments: Record<string, unknown>;
  status: "ok" | "error" | "skipped";
  summary: string;
  citations: ChatCitation[];
  result: Record<string, unknown>;
};

export type ChatEvent = {
  event_type: string;
  created_at: string;
  message: string;
  tool?: string | null;
  turn?: number | null;
  status?: "ok" | "error" | "skipped" | null;
  payload: Record<string, unknown>;
};

export type ChatRunLink = {
  flow: "ingest" | "lint" | "query";
  run_id: string;
  status: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
};

export type ChatTurnRecord = {
  index: number;
  created_at: string;
  user_message: ChatMessageItem;
  assistant_message: ChatMessageItem;
  citations: ChatCitation[];
  hidden_evidence_count: number;
  citation_warnings: string[];
  tool_trace: ChatToolTraceItem[];
  events: ChatEvent[];
  run_links: ChatRunLink[];
  memory_used: unknown[];
  memory_candidates: unknown[];
  memory_writes: unknown[];
  stats: Record<string, unknown>;
  warnings: string[];
};

export type ChatResponse = {
  schema_version: "chat_response.v1";
  session_id?: string | null;
  answer: string;
  messages: ChatMessageItem[];
  citations: ChatCitation[];
  hidden_evidence_count: number;
  citation_warnings: string[];
  tool_trace: ChatToolTraceItem[];
  events: ChatEvent[];
  run_links: ChatRunLink[];
  stats: Record<string, unknown>;
  warnings: string[];
};

export type ChatStreamEvent = {
  schema_version: "chat_stream_event.v1";
  event: "stage" | "tool" | "answer_delta" | "final" | "error";
  message: string;
  stage?: string | null;
  tool?: string | null;
  status?: string | null;
  response?: ChatResponse | null;
  error?: Record<string, unknown>;
  payload?: Record<string, unknown>;
};

export type ChatSessionSummary = {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  message_count: number;
  last_message: string;
  last_ingest_run_id?: string | null;
  last_ingested_at?: string | null;
  ingest_candidate?: ChatIngestCandidate | null;
};

export type ChatIngestCandidate = {
  should_ingest: boolean;
  reason: string;
  user_turns: number;
  assistant_turns: number;
  citation_count: number;
  signal_count: number;
  signals: string[];
};

export type ChatSessionRecord = {
  schema_version: "chat_session.v1";
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  status?: "active" | "closed";
  closed_at?: string | null;
  last_ingest_run_id?: string | null;
  last_ingested_at?: string | null;
  ingest_candidate?: ChatIngestCandidate | null;
  messages: ChatMessageItem[];
  turns: ChatTurnRecord[];
  citations: ChatCitation[];
  hidden_evidence_count: number;
  citation_warnings: string[];
  tool_trace: ChatToolTraceItem[];
  events: ChatEvent[];
  run_links: ChatRunLink[];
  memory_used: unknown[];
  memory_candidates: unknown[];
  memory_writes: unknown[];
  stats: Record<string, unknown>;
  warnings: string[];
};

export type ChatSessionListResponse = {
  sessions: ChatSessionSummary[];
};

export type ChatSessionDeleteResponse = {
  deleted: boolean;
  session_id: string;
};

export type WorkflowResponse = {
  flow: "ingest" | "lint" | "query";
  execution: "direct" | "queued";
  status: string;
  run_id?: string | null;
  run?: import("../types").RunRecord | null;
  result?: Record<string, unknown> | null;
};

export type ChatSessionWorkflowResponse = {
  session: ChatSessionRecord;
  ingest_started: boolean;
  run_id?: string | null;
  status?: string | null;
  reason: string;
};

export type PageSummary = {
  path: string;
  canonical_path?: string | null;
  directory: string;
  title: string;
  role?: string | null;
  updated?: string | null;
  entities: string[];
  summary: string;
  headings: string[];
};

export type PageDetail = {
  path: string;
  content: string;
  metadata: Record<string, string>;
  summary: PageSummary;
  outgoing_pages: PageRelation[];
  incoming_pages: PageRelation[];
};

export type PageRelation = {
  source: string;
  target: string;
  target_path?: string | null;
  resolved: boolean;
};

export type ReportSummary = {
  path: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  title: string;
  kind: string;
  updated?: string | null;
  size: number;
  preview: string;
};

export type ReportDetail = {
  path: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  content: string;
  summary: ReportSummary;
};

export type TokenMetricGroup = {
  name: string;
  call_count: number;
  prompt_tokens: number;
  prompt_cached_tokens: number;
  prompt_cache_rate?: number | null;
  prompt_stable_chars?: number;
  prompt_dynamic_chars?: number;
  dynamic_to_stable_ratio?: number | null;
  payload_char_total?: number;
  completion_tokens: number;
  total_tokens: number;
  elapsed_seconds: number;
  tokens_per_second?: number | null;
};

export type TokenPayloadFieldGroup = {
  name: string;
  call_count: number;
  payload_chars: number;
  top_call_count: number;
};

export type TokenCallRecord = {
  flow?: string;
  run_id?: string;
  agent?: string;
  provider?: string;
  model?: string;
  connector?: string;
  source_file?: string;
  segment_index?: number | null;
  segment_title?: string | null;
  segment_chars?: number | null;
  page_paths?: string[];
  prompt_tokens: number;
  prompt_cached_tokens: number;
  prompt_cache_rate?: number | null;
  prompt_stable_chars?: number;
  prompt_dynamic_chars?: number;
  dynamic_to_stable_ratio?: number | null;
  payload_char_total?: number;
  payload_top_field?: string | null;
  payload_char_breakdown?: Record<string, number>;
  completion_tokens: number;
  total_tokens: number;
  elapsed_seconds: number;
  tokens_per_second?: number | null;
};

export type TokenAnalysis = {
  schema_version: string;
  record_count: number;
  totals: TokenMetricGroup;
  by_flow: TokenMetricGroup[];
  by_agent: TokenMetricGroup[];
  by_source: TokenMetricGroup[];
  by_connector: TokenMetricGroup[];
  by_model: TokenMetricGroup[];
  by_page: TokenMetricGroup[];
  by_payload_field: TokenPayloadFieldGroup[];
  top_calls: TokenCallRecord[];
  recent_runs: Array<TokenMetricGroup & { run_id: string; flow?: string; created_at?: string | null; finished_at?: string | null }>;
};

export type ProjectDoc = {
  path: string;
  content: string;
};
