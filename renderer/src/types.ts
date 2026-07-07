export type ViewName = "chat" | "overview" | "sources" | "wiki" | "ingest" | "lint" | "query" | "graph" | "reports" | "tokens" | "settings";

export type Language = "en" | "zh";

export type RunRecord = {
  run_id: string;
  vault_id?: string | null;
  vault_name?: string | null;
  vault_path?: string | null;
  flow: "ingest" | "lint" | "query";
  status:
    | "created"
    | "queued"
    | "running"
    | "waiting_external_service"
    | "waiting_model"
    | "writing"
    | "linting"
    | "completed"
    | "failed"
    | "cancelling"
    | "cancelled"
    | "partially_failed";
  stage: string;
  current_item?: string | null;
  message: string;
  started_at: string;
  updated_at: string;
  last_heartbeat_at: string;
  finished_at?: string | null;
  elapsed_seconds: number;
  progress: { total?: number | null; completed: number; current?: string | null };
  metrics: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  error?: string | null;
  error_info?: RunErrorInfo | null;
  cancel_requested: boolean;
};

export type RunEvent = {
  run_id: string;
  sequence: number;
  created_at: string;
  event_type: string;
  status: RunRecord["status"];
  stage: string;
  message: string;
  current_item?: string | null;
  progress: RunRecord["progress"];
  metrics: Record<string, unknown>;
  payload: Record<string, unknown>;
};

export type RunErrorInfo = {
  code?: string;
  category?: string;
  message?: string;
  retryable?: boolean;
  hint?: string;
  error_type?: string;
};
