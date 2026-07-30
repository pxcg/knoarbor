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
  raw_record_id?: string | null;
  raw_revision_id?: string | null;
  source_record_id?: string | null;
  processing_record_id?: string | null;
  original_source_path?: string | null;
  source_unit_count?: number;
};

export type PageDetail = {
  path: string;
  content: string;
  metadata: Record<string, string>;
  summary: PageSummary;
  default_view?: "raw" | "wiki" | string;
  raw_content?: string | null;
  wiki_content?: string | null;
  raw_record_id?: string | null;
  raw_revision_id?: string | null;
  source_record_id?: string | null;
  processing_record_id?: string | null;
  original_source_path?: string | null;
  source_unit_count?: number;
  outgoing_pages: PageRelation[];
  incoming_pages: PageRelation[];
  editable_projection?: ProjectionEditorState | null;
  editable_raw?: RawRevisionEditorState | null;
};

export type ProjectionEvidenceView = {
  excerpt: string;
  source_path?: string | null;
  source_unit_id?: string | null;
  source_unit_index?: number | null;
};

export type ProjectionClaimEdit = {
  id: string;
  claim: string;
};

export type ProjectionClaimView = ProjectionClaimEdit & {
  evidence: ProjectionEvidenceView[];
};

export type ProjectionEntityEdit = {
  atom_id?: string | null;
  name: string;
  aliases: string[];
};

export type ProjectionRelationObjectEdit = {
  atom_id?: string | null;
  name: string;
};

export type ProjectionRelationEdit = {
  id?: string | null;
  subject: ProjectionRelationObjectEdit;
  predicate: string;
  object: ProjectionRelationObjectEdit;
  source_claim_ids: string[];
};

export type ProjectionEdit = {
  schema_version: "projection_edit.v1";
  base_revision_id: string;
  synthesis: string;
  claims: ProjectionClaimEdit[];
  entities: ProjectionEntityEdit[];
  relations: ProjectionRelationEdit[];
};

export type ProjectionEditorState = Omit<ProjectionEdit, "schema_version" | "claims"> & {
  schema_version: "projection_editor.v1";
  claims: ProjectionClaimView[];
};

export type RawRevisionEditorState = {
  schema_version: "raw_revision_editor.v1";
  base_revision_id: string;
  content: string;
  source_unit_count: number;
  evidence_span_count: number;
};

export type RawRevisionEdit = {
  schema_version: "raw_revision_edit.v1";
  base_revision_id: string;
  content: string;
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
