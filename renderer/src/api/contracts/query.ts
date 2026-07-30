export type QueryResult = {
  path: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  title: string;
  score: number;
  relevance: "high" | "medium" | "low";
  matched_fields: string[];
  matched_terms: Record<string, string[]>;
  reason: string;
  atom_traces: Array<{
    atom_id: string;
    atom_type: "claim" | "relation" | "entity" | "evidence";
    text: string;
    source_record_id: string;
    raw_record_id?: string | null;
    raw_revision_id?: string | null;
    source_unit_ids: string[];
    processing_record_id?: string | null;
  }>;
};
export type QueryRawEvidence = {
  evidence_id: string;
  raw_record_id: string;
  raw_revision_id: string;
  source_unit_id: string;
  source_record_id: string;
  processing_record_id?: string;
  source_path?: string;
  unit_index?: number;
  unit_type?: string;
  title?: string;
  excerpt: string;
  content?: string;
  excerpt_hash?: string;
  char_start?: number | null;
  char_end?: number | null;
  source_unit_char_start?: number | null;
  source_unit_char_end?: number | null;
  structural_path?: string[];
  locator_atom_ids?: string[];
  locator_page_paths?: string[];
  relevance?: "high" | "medium" | "low";
  reason?: string;
};

export type QuerySearchResponse = {
  schema_version: "wiki_query.v4";
  query: string;
  status:
    | "candidates"
    | "no_match"
    | "index_unavailable"
    | "integrity_error"
    | "invalid_query"
    | "invalid_scope"
    | "resource_exhausted"
    | "cancelled";
  retrieval_mode: string;
  results: QueryResult[];
  raw_evidence: QueryRawEvidence[];
  context_pack: string;
  gaps: string[];
  warnings: string[];
  stats?: Record<string, unknown>;
  trace?: Record<string, unknown>;
  exhausted: boolean;
  continuation_cursor?: string | null;
  continuation_cursors: Record<string, string>;
  query_fingerprint: string;
  snapshot_generation: string;
};

export type QueryTrendResponse = {
  sample_size: number;
  no_result_count: number;
  low_confidence_count: number;
  repeated_gap_queries: Array<{ query: string; count: number }>;
};
