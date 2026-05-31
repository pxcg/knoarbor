import { useEffect, useMemo, useState } from "react";

import { getPage, getReport, runIngest, runIngestFile, runLint, type ReportDetail } from "../api/client";
import type { AppContext } from "../App";
import { ReportReadableView } from "../components/report/ReportReadableView";
import { localizeReportKind, localizeReportTitle } from "../components/reportLabels";
import { RunFlowGuide } from "../components/runs/RunPanels";
import { runStatusLabel } from "../components/runStatus";
import type { RunRecord } from "../types";

type Props = {
  context: AppContext;
  embedded?: boolean;
  mode?: "both" | "ingest" | "lint";
};

export function RunPage({ context, embedded = false, mode = "both" }: Props) {
  const [connectors, setConnectors] = useState("");
  const [inputFilePath, setInputFilePath] = useState("");
  const [inputScope, setInputScope] = useState("enabled");
  const [ingestWrite, setIngestWrite] = useState(false);
  const [ingestReport, setIngestReport] = useState(true);
  const [lintMode, setLintMode] = useState("structural");
  const [lintApplySafe, setLintApplySafe] = useState(true);
  const [lintApplyReviewed, setLintApplyReviewed] = useState(false);
  const [runOutput, setRunOutput] = useState(() => context.t("noRunYet"));
  const [trackedRunId, setTrackedRunId] = useState<string | null>(null);
  const [terminalNoticeRunId, setTerminalNoticeRunId] = useState<string | null>(null);
  const configReady = context.configExists;
  const isSingleMode = mode !== "both";

  useEffect(() => {
    if (!trackedRunId) return;
    const run = [...context.activeRuns, ...context.recentRuns].find((item) => item.run_id === trackedRunId);
    if (!run) return;
    const terminal = isTerminalRunStatus(run.status);
    if (terminal && terminalNoticeRunId === run.run_id) return;
    const reportPath = reportPathFromRun(run);
    context.setNotice({
      message: `${context.t(run.flow)} · ${runStatusLabel(run.status, context.t)}${run.message ? `：${run.message}` : ""}`,
      error: run.status === "failed",
      actionLabel: reportPath ? context.t("openReport") : context.t("openRuns"),
      onAction: reportPath ? () => context.openReport(reportPath) : () => context.navigate("runs"),
    });
    if (terminal) setTerminalNoticeRunId(run.run_id);
  }, [context, terminalNoticeRunId, trackedRunId]);

  async function runOperation(operation: () => Promise<unknown>) {
    if (!configReady) {
      const message = context.t("configRequired");
      setRunOutput(message);
      context.setNotice({ message, error: true });
      return;
    }
    setRunOutput(context.t("running"));
    try {
      const response = await operation();
      setRunOutput(formatRunOutput(response, context.t));
      const runId = runIdFromResponse(response);
      if (runId) {
        setTrackedRunId(runId);
        setTerminalNoticeRunId(null);
      }
      context.setNotice({
        message: context.t("runStarted"),
        actionLabel: context.t("openRuns"),
        onAction: () => context.navigate("runs"),
      });
      await context.loadVaultState(context.vaultPath);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRunOutput(message);
      context.setNotice({ message, error: true });
    }
  }

  return (
    <section className={embedded ? "embedded-section" : "view active"}>
      <RunFlowGuide context={context} mode={mode} />

      <div className={`panel-grid ${isSingleMode ? "single-run-grid" : ""}`}>
        {mode !== "lint" && <article className="panel run-card">
          <div className="panel-header">
            <div>
              <h2>{context.t("ingestTitle")}</h2>
              <p className="panel-copy">{context.t("ingestSubtitle")}</p>
            </div>
            <button
              className="button primary"
              disabled={!configReady || (inputScope === "file" && !inputFilePath.trim())}
              onClick={() =>
                runOperation(() =>
                  inputScope === "file"
                    ? runIngestFile({
                        config_path: context.configPath,
                        input_path: inputFilePath,
                        write: ingestWrite,
                        write_report: ingestReport,
                        append_ledger: ingestReport,
                      })
                    : runIngest({
                        config_path: context.configPath,
                        connector_names: connectorNames(inputScope, connectors),
                        write: ingestWrite,
                        write_report: ingestReport,
                        append_ledger: ingestReport,
                      }),
                )
              }
            >
              {context.t("runIngest")}
            </button>
          </div>
          <label className="field">
            <span>{context.t("inputsToRun")}</span>
            <select value={inputScope} onChange={(event) => setInputScope(event.target.value)}>
              <option value="enabled">{context.t("enabledConnectors")}</option>
              <option value="markdown">{context.t("markdownConnector")}</option>
              <option value="hermes">{context.t("hermesConnector")}</option>
              <option value="codex">{context.t("codexConnector")}</option>
              <option value="openclaw">{context.t("openclawConnector")}</option>
              <option value="claude_code">{context.t("claudeCodeConnector")}</option>
              <option value="generic_chat">{context.t("genericChatConnector")}</option>
              <option value="file">{context.t("singleFileInput")}</option>
              <option value="custom">{context.t("customConnectorList")}</option>
            </select>
          </label>
          {inputScope === "file" && (
            <label className="field">
              <span>{context.t("inputFilePath")}</span>
              <input value={inputFilePath} onChange={(event) => setInputFilePath(event.target.value)} placeholder={context.t("inputFilePathPlaceholder")} />
            </label>
          )}
          {inputScope === "custom" && (
            <label className="field">
              <span>{context.t("connectorNames")}</span>
              <input value={connectors} onChange={(event) => setConnectors(event.target.value)} placeholder={context.t("connectorNamesPlaceholder")} />
            </label>
          )}
          <p className="panel-copy">{context.t("runIngestCopy")}</p>
          <div className="switch-row">
            <label>
              <input type="checkbox" checked={ingestWrite} onChange={(event) => setIngestWrite(event.target.checked)} />
              <span>
                {context.t("writeApprovedPages")}
                <small>{context.t("writeApprovedPagesHint")}</small>
              </span>
            </label>
            <label>
              <input type="checkbox" checked={ingestReport} onChange={(event) => setIngestReport(event.target.checked)} />
              <span>
                {context.t("writeReport")}
                <small>{context.t("writeReportHint")}</small>
              </span>
            </label>
          </div>
        </article>}

        {mode !== "ingest" && <article className="panel run-card">
          <div className="panel-header">
            <div>
              <h2>{context.t("lintTitle")}</h2>
              <p className="panel-copy">{context.t("lintSubtitle")}</p>
            </div>
            <button
              className="button primary"
              disabled={!configReady}
              onClick={() =>
                runOperation(() =>
                  runLint({
                    obsidian_vault_path: context.vaultPath,
                    config_path: context.configPath,
                    mode: lintMode,
                    apply_safe_fixes: lintApplySafe,
                    auto_apply_reviewed_changes: lintApplyReviewed,
                    write_report: true,
                    append_ledger: true,
                    scope: {
                      scope_id: `ui:${new Date().toISOString()}`,
                      trigger: "manual",
                      source: { kind: "ui" },
                      changed_pages: [],
                      recommended_lint_modes: [lintMode],
                      reason: "Manual lint maintenance run from UI.",
                    },
                  }),
                )
              }
            >
              {context.t("runLint")}
            </button>
          </div>
          <label className="field">
            <span>{context.t("mode")}</span>
            <select value={lintMode} onChange={(event) => setLintMode(event.target.value)}>
              <option value="structural">{context.t("structuralRepair")}</option>
              <option value="quality">{context.t("qualityReview")}</option>
              <option value="full">{context.t("fullMaintenance")}</option>
            </select>
          </label>
          <div className="switch-row">
            <label>
              <input type="checkbox" checked={lintApplySafe} onChange={(event) => setLintApplySafe(event.target.checked)} />
              <span>
                {context.t("applySafeFixes")}
                <small>{context.t("applySafeFixesHint")}</small>
              </span>
            </label>
            <label>
              <input type="checkbox" checked={lintApplyReviewed} onChange={(event) => setLintApplyReviewed(event.target.checked)} />
              <span>
                {context.t("applyReviewedChanges")}
                <small>{context.t("applyReviewedChangesHint")}</small>
              </span>
            </label>
          </div>
          {!configReady && <p className="panel-copy warning">{context.t("configRequired")}</p>}
        </article>}
      </div>

      <article className="panel">
        <div className="panel-header">
          <h2>{context.t("runOutput")}</h2>
          <button className="button secondary" onClick={() => setRunOutput(context.t("noRunYet"))}>
            {context.t("clear")}
          </button>
        </div>
        <pre className="output">{runOutput}</pre>
      </article>
      <LatestWorkflowReport context={context} mode={mode} />
    </section>
  );
}

function runIdFromResponse(response: unknown): string | null {
  if (!response || typeof response !== "object") return null;
  const runId = (response as Record<string, unknown>).run_id;
  return typeof runId === "string" && runId ? runId : null;
}

function reportPathFromRun(run: RunRecord): string | null {
  for (const source of [run.result_summary, run.metadata]) {
    const report = source?.report_path;
    if (typeof report === "string" && report) return report;
  }
  return null;
}

function isTerminalRunStatus(status: RunRecord["status"]) {
  return ["completed", "failed", "cancelled", "partially_failed"].includes(status);
}

function LatestWorkflowReport({ context, mode }: { context: AppContext; mode: "both" | "ingest" | "lint" }) {
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const latest = useMemo(() => {
    const target = mode === "both" ? null : mode;
    return context.reports.find((report) => {
      const kind = report.kind.toLowerCase();
      if (!target) return kind.includes("ingest") || kind.includes("lint");
      return target === "ingest" ? kind.includes("ingest") : kind.includes("lint") || kind.includes("maintenance");
    });
  }, [context.reports, mode]);

  useEffect(() => {
    let cancelled = false;
    if (!latest) {
      setDetail(null);
      return;
    }
    getReport(context.vaultPath, latest.path)
      .then((report) => {
        if (!cancelled) setDetail(report);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [context.vaultPath, latest]);

  if (!detail) return null;
  return (
    <article className="panel latest-workflow-report">
      <div className="panel-header">
        <div>
          <h2>{context.t("latestRunArtifact")}</h2>
          <p className="panel-copy">{context.t("latestRunArtifactCopy")}</p>
        </div>
        <button className="button secondary" type="button" onClick={() => context.openReport(detail.path)}>
          {context.t("openReport")}
        </button>
      </div>
      <div className="report-summary-card">
        <strong>{localizeReportTitle(detail.summary.title || detail.path, detail.summary.kind, context.t)}</strong>
        <span>{localizeReportKind(detail.summary.kind, context.t)} · {detail.summary.path}</span>
      </div>
      <ReportReadableView
        content={detail.content}
        t={context.t}
        onOpenPage={context.openWikiPage}
        loadPage={(path) => getPage(context.vaultPath, path)}
        inlinePagePreview
      />
    </article>
  );
}

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function connectorNames(inputScope: string, customValue: string) {
  if (inputScope === "enabled") return null;
  if (["markdown", "hermes", "codex", "openclaw", "claude_code", "generic_chat"].includes(inputScope)) return [inputScope];
  const custom = splitList(customValue);
  return custom.length ? custom : null;
}

function formatRunOutput(response: unknown, t: (key: string) => string) {
  if (!response || typeof response !== "object") return String(response);
  const data = response as Record<string, unknown>;
  const lines: string[] = [];
  if (data.run_id) {
    lines.push(`${t("runId")}: ${data.run_id}`);
    lines.push(`${t("status")}: ${runStatusLabel(String(data.status || "running"), t)}`);
    lines.push(t("runStartedWatchMonitor"));
    lines.push("");
    lines.push(t("rawResponse"));
    lines.push(JSON.stringify(response, null, 2));
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
    lines.push(
      `${t("documentProcessing")}: ${stats.processed_count ?? 0} ${t("processed")}, ${stats.failed_count ?? 0} ${t("failed")}`,
    );
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

function arrayText(value: unknown, t: (key: string) => string) {
  return Array.isArray(value) && value.length ? value.join(", ") : t("none");
}

function formatNumber(value: unknown) {
  return typeof value === "number" ? value.toFixed(2) : String(value);
}
