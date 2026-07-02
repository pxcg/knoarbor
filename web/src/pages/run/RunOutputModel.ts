import { runStatusLabel } from "../../components/runStatus";
import type { RunRecord } from "../../types";

export function runIdFromResponse(response: unknown): string | null {
  if (!response || typeof response !== "object") return null;
  const runId = (response as Record<string, unknown>).run_id;
  return typeof runId === "string" && runId ? runId : null;
}

export function reportPathFromRun(run: RunRecord): string | null {
  for (const source of [run.result_summary, run.metadata]) {
    const report = source?.report_path;
    if (typeof report === "string" && report) return report;
  }
  return null;
}

export function isTerminalRunStatus(status: RunRecord["status"]) {
  return ["completed", "failed", "cancelled", "partially_failed"].includes(status);
}

export function connectorNames(inputScope: string, customValue: string) {
  if (inputScope === "enabled" || inputScope === "file" || inputScope === "folder") return null;
  if (inputScope !== "custom") return [inputScope];
  const custom = splitList(customValue);
  return custom.length ? custom : null;
}

export function formatRunOutput(response: unknown, t: (key: string) => string) {
  if (!response || typeof response !== "object") return String(response);
  const data = response as Record<string, unknown>;
  const lines: string[] = [];
  if (data.run_id) {
    lines.push(`${t("runId")}: ${data.run_id}`);
    lines.push(`${t("status")}: ${runStatusLabel(String(data.status || "running"), t)}`);
    lines.push(t("runStartedWatchMonitor"));
    return lines.join("\n");
  }
  if (data.schema_version) lines.push(`${t("schema")}: ${data.schema_version}`);
  if (data.stats && typeof data.stats === "object") {
    const stats = data.stats as Record<string, unknown>;
    if (stats.source_count !== undefined) lines.push(`${t("sourcesProcessed")}: ${stats.source_count}`);
    if (stats.segment_count !== undefined) lines.push(`${t("segments")}: ${stats.segment_count}`);
    if (stats.failed_segment_count !== undefined) lines.push(`${t("failedSegments")}: ${stats.failed_segment_count}`);
    if (stats.written_count !== undefined) lines.push(`${t("writtenPages")}: ${stats.written_count}`);
  }
  if (data.metrics && typeof data.metrics === "object") {
    const metrics = data.metrics as Record<string, unknown>;
    const semantic = (metrics.semantic || {}) as Record<string, unknown>;
    if (metrics.elapsed_seconds !== undefined) lines.push(`${t("elapsed")}: ${formatNumber(metrics.elapsed_seconds)}s`);
    if (semantic.total_tokens !== undefined) lines.push(`${t("totalTokens")}: ${semantic.total_tokens}`);
    if (semantic.tokens_per_second !== undefined) lines.push(`${t("tokensPerSecond")}: ${formatNumber(semantic.tokens_per_second)}`);
  }
  if (data.document_processing && typeof data.document_processing === "object") {
    const processing = data.document_processing as Record<string, unknown>;
    const stats = (processing.stats || {}) as Record<string, unknown>;
    lines.push(`${t("documentProcessing")}: ${stats.processed_count ?? 0} ${t("processed")}, ${stats.failed_count ?? 0} ${t("failed")}`);
  }
  if (Array.isArray(data.results)) {
    lines.push(`${t("sourcesProcessed")}: ${data.results.length}`);
    for (const item of data.results as Array<Record<string, unknown>>) {
      lines.push("");
      lines.push(`${t("source")}: ${item.source_id || item.source_file || t("unknown")}`);
      lines.push(`${t("status")}: ${item.status || "completed"}`);
      if (item.segmentation && typeof item.segmentation === "object") {
        const segmentation = item.segmentation as Record<string, unknown>;
        lines.push(`${t("segments")}: ${segmentation.segment_count ?? 0} · ${t("mode")}: ${segmentation.mode ?? "none"}`);
      }
      lines.push(`${t("touchedPages")}: ${arrayText(item.touched_pages, t)}`);
      lines.push(`${t("createdPages")}: ${arrayText(item.created_pages, t)}`);
      lines.push(`${t("updatedPages")}: ${arrayText(item.updated_pages, t)}`);
      if (item.report_path) lines.push(`${t("report")}: ${item.report_path}`);
      if (item.scoped_lint_result && typeof item.scoped_lint_result === "object") {
        const lint = item.scoped_lint_result as Record<string, unknown>;
        lines.push(`${t("scopedLint")}: ${lint.issue_count ?? 0} ${t("issues")}`);
      }
    }
  } else {
    if (data.report_path) lines.push(`${t("report")}: ${data.report_path}`);
    if (data.ledger_path) lines.push(`${t("ledger")}: ${data.ledger_path}`);
    if (data.policy_decision && typeof data.policy_decision === "object") {
      const policy = data.policy_decision as Record<string, unknown>;
      lines.push(`${t("policy")}: ${policy.mode || t("unknown")} · ${t("triggered")}=${String(policy.triggered)}`);
    }
    if (data.deterministic_lint && typeof data.deterministic_lint === "object") {
      const lint = data.deterministic_lint as Record<string, unknown>;
      const issues = Array.isArray(lint.issues) ? lint.issues.length : 0;
      lines.push(`${t("baseCheckIssues")}: ${issues}`);
    }
    if (Array.isArray(data.written_pages)) lines.push(`${t("writtenPages")}: ${arrayText(data.written_pages, t)}`);
    if (Array.isArray(data.applied_operations)) lines.push(`${t("appliedOperations")}: ${data.applied_operations.length}`);
  }
  lines.push("");
  lines.push(t("rawResponse"));
  lines.push(JSON.stringify(response, null, 2));
  return lines.join("\n");
}

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function arrayText(value: unknown, t: (key: string) => string) {
  return Array.isArray(value) && value.length ? value.join(", ") : t("none");
}

function formatNumber(value: unknown) {
  return typeof value === "number" ? value.toFixed(2) : String(value);
}
