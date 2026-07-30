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
  api_key: string;
  model: string;
  json_mode: boolean;
  tls_ca_file: string;
  context_window?: number | null;
  max_output_tokens?: number | null;
  extra_body?: Record<string, unknown>;
};

export type ConfigImageProvider = {
  name: string;
  adapter: "sensenova_image" | "openai_chat_image";
  base_url: string;
  endpoint_path: string;
  api_key: string;
  model: string;
  tls_ca_file: string;
  resolution: string;
  num_inference_steps?: number | null;
  guidance?: number | null;
  extra_body?: Record<string, unknown>;
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

export type ModelApplyCapabilitiesResponse = {
  schema_version: "model_apply_capabilities.v1";
  provider: string;
  config_path: string;
  saved: boolean;
  applied: Record<string, unknown>;
};

export type ModelProviderProbeState = {
  discovery?: ModelDiscoveryResponse;
  lastAction?: "discover";
};

export type ImageProviderProbeResponse = {
  schema_version: "image_provider_probe.v1";
  provider: string;
  model: string;
  adapter: string;
  status: "ok" | "error";
  available: boolean;
  message: string;
  elapsed_ms: number;
  image_count: number;
  mime_types: string[];
  error_code?: string | null;
  retryable: boolean;
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
  detected_chat_source_dirs: Record<string, string[]>;
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

export type GraphResponse = {
  vault_path: string;
  graph_kind?: "page";
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

