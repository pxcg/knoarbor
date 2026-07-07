import type { RunEvent, RunRecord } from "../../types";

export type FlowNode = {
  key: string;
  label: string;
  kind?: "workflow" | "agent";
};

export type RunSourceInfo = {
  label: string;
  detail?: string;
};

const INGEST_STAGE_KEYS = new Set([
  "input",
  "segment",
  "normalize_agent",
  "atom_agent",
  "retrieval",
  "plan_agent",
  "draft_agent",
  "review_agent",
  "write_gate",
  "write",
]);

const LINT_STAGE_KEYS = new Set(["scan", "diagnose", "review", "execute", "verify", "report"]);

const SOURCE_EVENT_TYPES = new Set(["source_started", "source_processing", "segments_created", "source_queued"]);

export function dedupeRuns(runs: RunRecord[]): RunRecord[] {
  const seen = new Set<string>();
  const result: RunRecord[] = [];
  for (const run of runs) {
    if (seen.has(run.run_id)) continue;
    seen.add(run.run_id);
    result.push(run);
  }
  return result;
}

export function flowStages(flow: RunRecord["flow"]): FlowNode[] {
  if (flow === "lint") {
    return [
      { key: "queued", label: "runStageQueued", kind: "workflow" },
      { key: "scan", label: "runStageScan", kind: "workflow" },
      { key: "diagnose", label: "runStageDiagnose", kind: "agent" },
      { key: "review", label: "runStageReview", kind: "agent" },
      { key: "execute", label: "runStageExecute", kind: "workflow" },
      { key: "verify", label: "runStageVerify", kind: "workflow" },
      { key: "report", label: "runStageReport", kind: "workflow" },
      { key: "done", label: "runStageDone", kind: "workflow" },
    ];
  }
  if (flow === "query") {
    return [
      { key: "queued", label: "runStageQueued", kind: "workflow" },
      { key: "search", label: "runStageSearch", kind: "workflow" },
      { key: "pack", label: "runStagePack", kind: "workflow" },
      { key: "done", label: "runStageDone", kind: "workflow" },
    ];
  }
  return [
    { key: "queued", label: "runStageQueued", kind: "workflow" },
    { key: "input", label: "runStageInput", kind: "workflow" },
    { key: "segment", label: "runStageSegment", kind: "workflow" },
    { key: "normalize_agent", label: "runStageNormalizeAgent", kind: "agent" },
    { key: "atom_agent", label: "runStageAtomAgent", kind: "agent" },
    { key: "retrieval", label: "runStageRetrieval", kind: "workflow" },
    { key: "plan_agent", label: "runStagePlanAgent", kind: "agent" },
    { key: "draft_agent", label: "runStageDraftAgent", kind: "agent" },
    { key: "review_agent", label: "runStageReviewAgent", kind: "agent" },
    { key: "write_gate", label: "runStageWriteGate", kind: "workflow" },
    { key: "write", label: "runStageWrite", kind: "workflow" },
    { key: "done", label: "runStageDone", kind: "workflow" },
  ];
}

export function currentStageKey(run: RunRecord): string {
  if (run.status === "completed" || run.status === "cancelled") return "done";
  if (run.status === "queued" || run.stage === "queued") return "queued";
  const stage = `${run.stage || ""} ${run.current_item || ""}`;
  if (run.flow === "ingest" && INGEST_STAGE_KEYS.has(run.stage)) return run.stage;
  if (run.flow === "lint" && LINT_STAGE_KEYS.has(run.stage)) return run.stage;
  if (stage.includes("source_normalize")) return "normalize_agent";
  if (stage.includes("wiki_atom_extract")) return "atom_agent";
  if (stage.includes("wiki_page_plan")) return "plan_agent";
  if (stage.includes("wiki_relation")) return "plan_agent";
  if (stage.includes("wiki_draft_compile")) return "draft_agent";
  if (stage.includes("ingest_draft_review")) return "review_agent";
  if (stage.includes("retrieval") || stage.includes("query")) return "retrieval";
  if (run.status === "waiting_model" || stage.includes("semantic") || stage.includes("model") || stage.includes("relation") || stage.includes("draft")) {
    if (run.flow === "lint") {
      if (stage.includes("review")) return "review";
      if (stage.includes("draft")) return "execute";
      return "diagnose";
    }
    return run.flow === "ingest" ? "review_agent" : "diagnose_agent";
  }
  if (stage.includes("document") || stage.includes("preprocess")) return "input";
  if (stage.includes("segment")) return "segment";
  if (stage.includes("lint") || stage.includes("scan") || stage.includes("quality")) return run.flow === "lint" ? "scan" : "write";
  if (stage.includes("write") || stage.includes("report") || stage.includes("checkpoint")) return "write";
  if (run.flow === "query") {
    if (stage.includes("pack") || stage.includes("context")) return "pack";
    return "search";
  }
  return run.flow === "lint" ? "scan" : "input";
}

export function eventNodeKey(event: RunEvent, flow: RunRecord["flow"]): string {
  const ingestStep = stringValue(asRecord(event.payload).ingest_step);
  if (flow === "ingest" && ingestStep && INGEST_STAGE_KEYS.has(ingestStep)) return ingestStep;
  const lintStep = stringValue(asRecord(event.payload).lint_step);
  if (flow === "lint" && lintStep && LINT_STAGE_KEYS.has(lintStep)) return lintStep;
  const text = `${event.stage || ""} ${event.current_item || ""} ${event.message || ""} ${event.event_type || ""}`.toLowerCase();
  if (event.status === "completed") return "done";
  if (text.includes("source_normalize")) return "normalize_agent";
  if (text.includes("wiki_atom_extract")) return "atom_agent";
  if (text.includes("wiki_page_plan")) return "plan_agent";
  if (text.includes("wiki_relation")) return "plan_agent";
  if (text.includes("wiki_draft_compile")) return "draft_agent";
  if (text.includes("ingest_draft_review")) return "review_agent";
  if (text.includes("lint_diagnose") || text.includes("quality_diagnose") || text.includes("diagnose")) return flow === "lint" ? "diagnose" : "diagnose_agent";
  if (text.includes("review")) return flow === "lint" ? "review" : "review_agent";
  if (text.includes("query returned") || text.includes("retrieval") || text.includes("candidate") || text.includes("search")) {
    return flow === "query" ? "search" : "retrieval";
  }
  if (text.includes("segment")) return "segment";
  if (text.includes("standardizing") || text.includes("normalizing") || text.includes("document") || text.includes("preprocess")) return "input";
  if (text.includes("report")) return flow === "lint" ? "report" : "write";
  if (text.includes("write") || text.includes("checkpoint")) return flow === "lint" ? "execute" : "write";
  if (flow === "query" && (text.includes("pack") || text.includes("context"))) return "pack";
  if (event.status === "queued" || text.includes("queued")) return "queued";
  return currentStageKey({
    run_id: event.run_id,
    flow,
    status: event.status,
    stage: event.stage,
    current_item: event.current_item,
    message: event.message,
    started_at: event.created_at,
    updated_at: event.created_at,
    last_heartbeat_at: event.created_at,
    elapsed_seconds: 0,
    progress: event.progress,
    metrics: event.metrics,
    result_summary: {},
    cancel_requested: false,
  });
}

export function runStageMetrics(run: RunRecord): Array<{ label: string; value: string }> {
  const metrics = asRecord(run.metrics);
  const summary = asRecord(run.result_summary);
  const values: Array<{ label: string; value: string }> = [];
  const semanticCalls = numberValue(metrics.semantic_call_count) ?? numberValue(summary.semantic_calls);
  const totalTokens = numberValue(metrics.total_tokens) ?? numberValue(summary.total_tokens);
  const writtenPages = numberValue(summary.written_pages) ?? numberValue(asRecord(summary.stats).written_count);
  if (semanticCalls !== undefined) values.push({ label: "semanticCallsShort", value: String(semanticCalls) });
  if (totalTokens !== undefined) values.push({ label: "totalTokensShort", value: totalTokens.toLocaleString() });
  if (writtenPages !== undefined) values.push({ label: "writtenPagesShort", value: String(writtenPages) });
  return values;
}

export function runProgressPercent(run: RunRecord, events: RunEvent[]): number | undefined {
  const eventProgress = events
    .slice()
    .reverse()
    .map((event) => event.progress)
    .find((progress) => progress && typeof progress.total === "number" && progress.total > 0);
  const progress = eventProgress || run.progress;
  if (progress && typeof progress.total === "number" && progress.total > 0 && typeof progress.completed === "number") {
    return Math.min(100, Math.max(0, Math.round((progress.completed / progress.total) * 100)));
  }
  const stages = flowStages(run.flow);
  const currentIndex = stages.findIndex((stage) => stage.key === currentStageKey(run));
  if (currentIndex < 0) return undefined;
  if (run.status === "completed") return 100;
  return Math.min(99, Math.max(0, Math.round((currentIndex / Math.max(1, stages.length - 1)) * 100)));
}

export function currentSourceInfo(run: RunRecord, events: RunEvent[], t: (key: string) => string): RunSourceInfo {
  const sourceEvents = events
    .slice()
    .reverse()
    .filter((event) => SOURCE_EVENT_TYPES.has(event.event_type) && typeof event.current_item === "string" && event.current_item.trim());
  const item = sourceEvents[0]?.current_item || sourceFromRunMetadata(run);
  if (!item) return { label: t("notAvailable") };
  return sourceInfoFromValue(item, t);
}

export function runResultItems(run: RunRecord, t: (key: string) => string): Array<{ label: string; value: string }> {
  const summary = asRecord(run.result_summary);
  const stats = asRecord(summary.stats);
  const items: Array<{ label: string; value: string }> = [];
  const writtenPages = writtenPageCount(summary.written_pages) ?? numberValue(stats.written_count);
  const failedSources = numberValue(stats.failed_count);
  const failedSegments = numberValue(stats.failed_segment_count);
  const processed = numberValue(stats.processed_count);
  const semanticCalls = numberValue(summary.semantic_calls) ?? numberValue(asRecord(run.metrics).semantic_call_count);
  const totalTokens = numberValue(summary.total_tokens) ?? numberValue(asRecord(run.metrics).total_tokens);
  if (processed !== undefined) items.push({ label: t("processed"), value: String(processed) });
  if (writtenPages !== undefined) items.push({ label: t("writtenPages"), value: String(writtenPages) });
  if (failedSources !== undefined) items.push({ label: t("failedSources"), value: String(failedSources) });
  if (failedSegments !== undefined) items.push({ label: t("failedSegments"), value: String(failedSegments) });
  if (semanticCalls !== undefined) items.push({ label: t("semanticCallsShort"), value: semanticCalls.toLocaleString() });
  if (totalTokens !== undefined) items.push({ label: t("totalTokensShort"), value: totalTokens.toLocaleString() });
  const reportPath = reportPathForRun(run);
  if (reportPath) items.push({ label: t("report"), value: reportPath });
  return items;
}

export function ingestRecoveryFacts(run: RunRecord, t: (key: string) => string) {
  const stats = asRecord(run.result_summary?.stats);
  const facts: string[] = [];
  const failedCount = numberValue(stats.failed_count);
  const failedSegments = numberValue(stats.failed_segment_count);
  const documentFailures = numberValue(stats.document_processing_failed_count);
  const processedCount = numberValue(stats.processed_count);
  const writtenCount = numberValue(stats.written_count);
  if (failedCount !== undefined) facts.push(`${t("failedSources")}: ${failedCount}`);
  if (failedSegments !== undefined) facts.push(`${t("failedSegments")}: ${failedSegments}`);
  if (documentFailures !== undefined) facts.push(`${t("documentProcessingFailures")}: ${documentFailures}`);
  if (processedCount !== undefined) facts.push(`${t("processed")}: ${processedCount}`);
  if (writtenCount !== undefined) facts.push(`${t("writtenPages")}: ${writtenCount}`);
  if (run.metadata?.recovery_of_run_id) facts.push(`${t("recoveryOf")}: ${String(run.metadata.recovery_of_run_id)}`);
  return facts;
}

export function canRecoverRun(run: RunRecord) {
  const recovery = asRecord(run.result_summary?.recovery);
  return run.flow === "ingest" && recovery.available === true;
}

export function reportPathForRun(run: RunRecord): string | null {
  const path = run.result_summary?.report_path;
  return typeof path === "string" && path ? path : null;
}

export function currentStageLabel(run: RunRecord, t: (key: string) => string): string {
  const current = currentStageKey(run);
  const node = flowStages(run.flow).find((stage) => stage.key === current);
  return node ? t(node.label) : displayStageLabel(run.stage || run.status, t);
}

export function stageLabel(run: { stage?: string | null; status?: string | null; current_item?: string | null }, t: (key: string) => string): string {
  const stage = run.stage || "";
  const label = displayStageLabel(stage || run.status || "", t);
  const current = run.current_item;
  return current ? `${label} · ${t("currentItem")}: ${current}` : label;
}

export function localizeRunEventMessage(message: string | null | undefined, eventType: string, t: (key: string) => string): string {
  const value = (message || eventType || "").trim();
  if (!value || t("language") !== "语言") return value;
  const direct: Record<string, string> = {
    "Calling model for source_normalize.": "调用模型：资料标准化。",
    "Calling model for wiki_atom_extract.": "调用模型：知识原子提取。",
    "Calling model for wiki_page_plan.": "调用模型：页面规划。",
    "Calling model for wiki_relation_plan.": "调用模型：页面关系规划。",
    "Calling model for wiki_draft_compile.": "调用模型：页面编译。",
    "Calling model for ingest_draft_review.": "调用模型：草稿评审。",
    "Standardizing source document.": "标准化资料文档。",
    "Extracting knowledge atoms.": "提取知识原子。",
    "Compiling wiki draft.": "编译 Wiki 页面草稿。",
    "Writing wiki pages.": "写入 Wiki 页面。",
  };
  if (direct[value]) return direct[value];
  const modelCall = value.match(/^Calling model for ([a-z0-9_:-]+)\.?$/i);
  if (modelCall) return `调用模型：${displayStageLabel(modelCall[1], t)}。`;
  return value;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function numberValue(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

export function writtenPageCount(value: unknown): number | undefined {
  if (typeof value === "number") return value;
  if (Array.isArray(value)) return value.length;
  return undefined;
}

function displayStageLabel(stage: string, t: (key: string) => string): string {
  if (!stage) return t("notAvailable");
  const normalized = stage.toLowerCase();
  const statusKey = `runStatus.${normalized}`;
  const statusLabel = t(statusKey);
  if (statusLabel !== statusKey) return statusLabel;
  if (normalized === "queued") return t("runStageQueued");
  if (normalized === "diagnose") return t("runStageDiagnose");
  if (normalized === "review") return t("runStageReview");
  if (normalized === "execute") return t("runStageExecute");
  if (normalized === "verify") return t("runStageVerify");
  if (normalized === "report") return t("runStageReport");
  if (normalized.includes("segment")) return t("runStageSegment");
  if (normalized.includes("semantic") || normalized.includes("model") || normalized.includes("relation") || normalized.includes("draft")) return t("runStageModel");
  if (normalized.includes("document") || normalized.includes("preprocess") || normalized.includes("normalizing")) return t("runStageInput");
  if (normalized.includes("scan") || normalized.includes("quality")) return t("runStageScan");
  if (normalized.includes("write") || normalized.includes("report") || normalized.includes("checkpoint")) return t("runStageWrite");
  if (normalized.includes("pack") || normalized.includes("context")) return t("runStagePack");
  if (normalized.includes("search") || normalized.includes("query")) return t("runStageSearch");
  return stage.replace(/_/g, " ");
}

function sourceFromRunMetadata(run: RunRecord): string {
  const metadata = asRecord(run.metadata);
  const summary = asRecord(run.result_summary);
  const connectorNames = Array.isArray(metadata.connector_names) ? metadata.connector_names.filter((item): item is string => typeof item === "string") : [];
  return (
    stringValue(summary.source_file) ||
    stringValue(summary.source_id) ||
    stringValue(metadata.input_path) ||
    stringValue(metadata.source_id) ||
    connectorNames[0] ||
    ""
  );
}

function sourceInfoFromValue(value: string, t: (key: string) => string): RunSourceInfo {
  const connector = connectorFromValue(value);
  const label = connectorLabel(connector, t);
  const detail = sourceDetail(value, connector);
  return { label, detail };
}

function connectorFromValue(value: string): string {
  const normalized = value.replace(/\\/g, "/").toLowerCase();
  const prefix = normalized.match(/^([a-z_]+):/);
  if (prefix) return prefix[1];
  if (normalized.includes("/.codex/")) return "codex";
  if (normalized.includes("/.hermes/")) return "hermes";
  if (normalized.includes("/.openclaw/")) return "openclaw";
  if (normalized.includes("/.claude/")) return "claude_code";
  if (normalized.endsWith(".md") || normalized.endsWith(".markdown")) return "markdown";
  return "sources";
}

function connectorLabel(connector: string, t: (key: string) => string): string {
  const key = `${connector}Connector`;
  const label = t(key);
  if (label !== key) return label;
  if (connector === "claude_code") return "Claude Code";
  if (connector === "generic_chat") return t("genericChatConnector");
  return connector === "sources" ? t("source") : connector;
}

function sourceDetail(value: string, connector: string): string | undefined {
  if (/^[a-z_]+:[0-9a-f]{8,}$/i.test(value)) return undefined;
  const compact = compactPath(value);
  if (!compact || compact === connector) return undefined;
  if (/^[a-z_]+:[^/\\]+$/i.test(value)) return undefined;
  return compact;
}

function compactPath(value: string): string {
  const normalized = value.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts.length ? parts.slice(-2).join("/") : value;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
