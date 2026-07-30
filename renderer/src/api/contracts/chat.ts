export type ChatMessageItem = {
  message_id?: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name?: string | null;
};
export type ChatCitation = {
  kind: "raw_evidence" | "page" | "report" | "run";
  role?: "primary" | "supporting" | "source" | "further_reading" | null;
  path?: string | null;
  title?: string | null;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  run_id?: string | null;
  evidence_id?: string | null;
  raw_revision_id?: string | null;
  source_unit_id?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  spans?: Array<{
    char_start: number;
    char_end: number;
  }>;
  reason?: string;
};

export type ChatCitationResolution = {
  index: number;
  status: "resolved" | "unavailable";
  text?: string | null;
  texts?: string[];
};

export type ChatCitationResolveResponse = {
  schema_version: "chat_citation_resolve_response.v1";
  resolutions: ChatCitationResolution[];
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
  turn_id: string;
  request_id: string;
  execution_id: string;
  created_at: string;
  user_message: ChatMessageItem;
  assistant_message: ChatMessageItem;
  answer_provenance: ChatAnswerProvenance;
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
  schema_version: "chat_response.v4";
  request_id: string;
  execution_id: string;
  session_id: string;
  session_revision: number;
  turn_id: string;
  answer: string;
  answer_provenance: ChatAnswerProvenance;
  citations: ChatCitation[];
  hidden_evidence_count: number;
  citation_warnings: string[];
  tool_trace: ChatToolTraceItem[];
  events: ChatEvent[];
  run_links: ChatRunLink[];
  stats: Record<string, unknown>;
  warnings: string[];
};

export type ChatAnswerMode = "knowledge_grounded" | "knowledge_grounded_with_gap" | "general_knowledge" | "knowledge_gap" | "clarification" | "direct_capability";
export type ChatAnswerProvenance = {
  mode: ChatAnswerMode;
  query_outcome: "candidates" | "no_match" | "index_unavailable" | "integrity_error" | "invalid_query" | "invalid_scope" | "resource_exhausted" | "cancelled" | "not_applicable";
  chat_outcome: "sufficient" | "partial" | "no_match" | "needs_clarification" | "planning_exhausted" | "resource_exhausted" | "tool_error" | "integrity_error" | "cancelled" | "direct";
};

export type ChatStreamEvent = {
  schema_version: "chat_stream_event.v1";
  event: "stage" | "tool" | "source" | "answer_delta" | "final" | "error";
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
  session_revision: number;
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
  schema_version: "chat_session.v4";
  session_id: string;
  session_revision: number;
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
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
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
  run?: import("../../types").RunRecord | null;
  result?: Record<string, unknown> | null;
};

export type ChatSessionWorkflowResponse = {
  session: ChatSessionRecord;
  ingest_started: boolean;
  run_id?: string | null;
  status?: string | null;
  reason: string;
};
