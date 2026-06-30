import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getPage, getReport, getSourceCatalog, ingestChatSession, listChatSessions, runIngest, runIngestFile, runIngestFolder, runLint, type ReportDetail } from "../api/client";
import type { AppContext } from "../appContext";
import { localizeReportKind, localizeReportTitle } from "../components/reportLabels";
import { ReportSummaryCard } from "../components/report/ReportSummaryCard";
import { RunFlowGuide } from "../components/runs/RunPanels";
import { runStatusLabel } from "../components/runStatus";
import { queryKeys } from "../queryKeys";
import { sortSourceConnectors, sourceTitle } from "../sourceCatalog";
import type { RunRecord } from "../types";

const ReportReadableView = lazy(() => import("../components/report/ReportReadableView").then((module) => ({ default: module.ReportReadableView })));

type Props = {
  context: AppContext;
  embedded?: boolean;
  mode?: "both" | "ingest" | "lint";
  showFlowGuide?: boolean;
};

export function RunPage({ context, embedded = false, mode = "both", showFlowGuide }: Props) {
  const [connectors, setConnectors] = useState("");
  const [inputFilePath, setInputFilePath] = useState("");
  const [inputFolderPath, setInputFolderPath] = useState("");
  const [inputScope, setInputScope] = useState("enabled");
  const [selectedChatSessionId, setSelectedChatSessionId] = useState("");
  const [lintMode, setLintMode] = useState("structural");
  const [runOutput, setRunOutput] = useState(() => context.t("noRunYet"));
  const [trackedRunId, setTrackedRunId] = useState<string | null>(null);
  const [terminalNoticeRunId, setTerminalNoticeRunId] = useState<string | null>(null);
  const configReady = context.configExists;
  const isSingleMode = mode !== "both";
  const shouldShowFlowGuide = showFlowGuide ?? (!embedded && mode === "both");
  const sourceCatalogQuery = useQuery({
    queryKey: queryKeys.sourceCatalog(context.configPath),
    queryFn: () => getSourceCatalog(context.configPath),
    enabled: mode !== "lint",
    staleTime: 60_000,
  });
  const connectorOptions = sortSourceConnectors(sourceCatalogQuery.data?.connectors || []);
  const chatSessionsQuery = useQuery({
    queryKey: ["run-chat-sessions", context.activeVaultId],
    queryFn: () => listChatSessions(context.activeVaultSelector, 50),
    enabled: mode !== "lint",
    staleTime: 30_000,
  });
  const chatSessions = chatSessionsQuery.data?.sessions || [];

  useEffect(() => {
    if (selectedChatSessionId && chatSessions.some((session) => session.session_id === selectedChatSessionId)) return;
    setSelectedChatSessionId(chatSessions[0]?.session_id || "");
  }, [chatSessions, selectedChatSessionId]);

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
      await context.loadVaultState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRunOutput(message);
      context.setNotice({ message, error: true });
    }
  }

  async function chooseInputFile() {
    if (!window.knoarborDesktop?.selectFile) return;
    const result = await window.knoarborDesktop.selectFile({
      defaultPath: inputFilePath || undefined,
      title: context.t("chooseInputFile"),
    });
    if (!result.canceled && result.path) setInputFilePath(result.path);
  }

  async function chooseInputFolder() {
    if (!window.knoarborDesktop?.selectDirectory) return;
    const result = await window.knoarborDesktop.selectDirectory({
      defaultPath: inputFolderPath || undefined,
      title: context.t("chooseInputFolder"),
    });
    if (!result.canceled && result.path) setInputFolderPath(result.path);
  }

  return (
    <section className={embedded ? "embedded-section" : "view active"}>
      {shouldShowFlowGuide && <RunFlowGuide context={context} mode={mode} />}

      <div className={`panel-grid ${isSingleMode ? "single-run-grid" : ""}`}>
        {mode !== "lint" && <article className="panel run-card">
          <div className="panel-header">
            <div>
              <h2>{context.t("ingestTitle")}</h2>
              <p className="panel-copy">{context.t("ingestSubtitle")}</p>
            </div>
            <button
              className="button primary"
              disabled={
                !configReady ||
                (inputScope === "file" && !inputFilePath.trim()) ||
                (inputScope === "folder" && !inputFolderPath.trim()) ||
                (inputScope === "knoarbor_chat" && !selectedChatSessionId)
              }
              onClick={() =>
                runOperation(() =>
                  inputScope === "knoarbor_chat"
                    ? ingestChatSession(context.activeVaultSelector, selectedChatSessionId)
                    : inputScope === "file"
                    ? runIngestFile({
                        config_path: context.configPath,
                        vault_id: context.activeVaultId,
                        input_path: inputFilePath,
                        write: true,
                        write_report: true,
                        append_ledger: true,
                      })
                    : inputScope === "folder"
                    ? runIngestFolder({
                        config_path: context.configPath,
                        vault_id: context.activeVaultId,
                        input_path: inputFolderPath,
                        write: true,
                        write_report: true,
                        append_ledger: true,
                      })
                    : runIngest({
                        config_path: context.configPath,
                        vault_id: context.activeVaultId,
                        connector_names: connectorNames(inputScope, connectors),
                        write: true,
                        write_report: true,
                        append_ledger: true,
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
              <option value="knoarbor_chat">{context.t("knoarborChatConnector")}</option>
              {connectorOptions.map((connector) => (
                <option value={connector.name} key={connector.name}>
                  {sourceTitle(connector.name, context.t)}
                </option>
              ))}
              <option value="file">{context.t("singleFileInput")}</option>
              <option value="folder">{context.t("singleFolderInput")}</option>
              <option value="custom">{context.t("customConnectorList")}</option>
            </select>
          </label>
          {inputScope === "knoarbor_chat" && (
            <label className="field">
              <span>{context.t("selectChatSession")}</span>
              <select value={selectedChatSessionId} onChange={(event) => setSelectedChatSessionId(event.target.value)} disabled={chatSessionsQuery.isLoading || !chatSessions.length}>
                {chatSessions.length ? chatSessions.map((session) => (
                  <option value={session.session_id} key={session.session_id}>
                    {session.title || session.session_id}
                  </option>
                )) : (
                  <option value="">{context.t("noChatSessionsToIngest")}</option>
                )}
              </select>
              <small>{context.t("knoarborChatInputHint")}</small>
            </label>
          )}
          {inputScope === "file" && (
            <label className="field">
              <span>{context.t("inputFilePath")}</span>
              <div className="run-path-row">
                <input value={inputFilePath} onChange={(event) => setInputFilePath(event.target.value)} placeholder={context.t("inputFilePathPlaceholder")} />
                {window.knoarborDesktop?.selectFile && (
                  <button className="button secondary" type="button" onClick={() => void chooseInputFile()}>
                    {context.t("chooseFile")}
                  </button>
                )}
              </div>
            </label>
          )}
          {inputScope === "folder" && (
            <label className="field">
              <span>{context.t("inputFolderPath")}</span>
              <div className="run-path-row">
                <input value={inputFolderPath} onChange={(event) => setInputFolderPath(event.target.value)} placeholder={context.t("inputFolderPathPlaceholder")} />
                {window.knoarborDesktop?.selectDirectory && (
                  <button className="button secondary" type="button" onClick={() => void chooseInputFolder()}>
                    {context.t("chooseFolder")}
                  </button>
                )}
              </div>
            </label>
          )}
          {inputScope === "custom" && (
            <label className="field">
              <span>{context.t("connectorNames")}</span>
              <input value={connectors} onChange={(event) => setConnectors(event.target.value)} placeholder={context.t("connectorNamesPlaceholder")} />
            </label>
          )}
          <p className="panel-copy">{context.t("runIngestCopy")}</p>
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
                    config_path: context.configPath,
                    vault_id: context.activeVaultId,
                    mode: lintMode,
                    apply_safe_fixes: true,
                    auto_apply_reviewed_changes: true,
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
        <pre className={`output ${runOutput === context.t("noRunYet") ? "output-idle" : ""}`}>{runOutput}</pre>
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
    getReport(context.activeVaultSelector, latest.path)
      .then((report) => {
        if (!cancelled) setDetail(report);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [context.activeVaultSelector, latest]);

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
      <ReportSummaryCard
        title={localizeReportTitle(detail.summary.title || detail.path, detail.summary.kind, context.t)}
        subtitle={`${localizeReportKind(detail.summary.kind, context.t)} · ${detail.summary.path}`}
      />
      <Suspense fallback={<p className="panel-copy">{context.t("loading")}</p>}>
        <ReportReadableView
          content={detail.content}
          t={context.t}
          onOpenPage={context.openWikiPage}
          loadPage={(path) => getPage(context.activeVaultSelector, path)}
          inlinePagePreview
        />
      </Suspense>
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
  if (inputScope === "enabled" || inputScope === "file" || inputScope === "folder") return null;
  if (inputScope !== "custom") return [inputScope];
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
