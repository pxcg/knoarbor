import { useEffect, useState } from "react";

import { cancelRun, getRunEvents, rerunFailedRun } from "../../api/client";
import type { AppContext } from "../../App";
import { LineIcon } from "../LineIcon";
import { runStatusClass, runStatusLabel } from "../runStatus";
import type { RunEvent, RunRecord } from "../../types";

export function ActiveRunsPanel({ context, includeRecoverable = false }: { context: AppContext; includeRecoverable?: boolean }) {
  const recoverableRecent = context.recentRuns.filter((run) => canRecoverRun(run));
  const runs = _dedupeRuns([...context.activeRuns, ...(includeRecoverable ? recoverableRecent.slice(0, 3) : [])]);
  if (!runs.length) {
    return (
      <article className="panel run-monitor-panel">
        <div className="panel-header compact">
          <div>
            <h2>{context.t("runMonitor")}</h2>
            <p className="panel-copy">{context.t("noActiveRuns")}</p>
          </div>
        </div>
      </article>
    );
  }
  return (
    <article className="panel run-monitor-panel">
      <div className="panel-header compact">
        <div>
          <h2>{context.t("runMonitor")}</h2>
          <p className="panel-copy">{context.t("runMonitorCopy")}</p>
        </div>
      </div>
      <div className="run-monitor-list">
        {runs.map((run) => (
          <RunMonitorItem key={run.run_id} context={context} run={run} />
        ))}
      </div>
    </article>
  );
}

function _dedupeRuns(runs: RunRecord[]): RunRecord[] {
  const seen = new Set<string>();
  const result: RunRecord[] = [];
  for (const run of runs) {
    if (seen.has(run.run_id)) continue;
    seen.add(run.run_id);
    result.push(run);
  }
  return result;
}

function RunMonitorItem({ context, run }: { context: AppContext; run: RunRecord }) {
  const total = run.progress?.total || 0;
  const completed = run.progress?.completed || 0;
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : undefined;
  const staleSeconds = Math.max(0, Math.round((Date.now() - Date.parse(run.last_heartbeat_at)) / 1000));
  const canRecover = canRecoverRun(run);
  const recoveryFacts = ingestRecoveryFacts(run, context.t);
  const reportPath = reportPathForRun(run);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [selectedNode, setSelectedNode] = useState<string>(() => currentStageKey(run));

  useEffect(() => {
    let cancelled = false;
    getRunEvents(context.vaultPath, run.run_id)
      .then((response) => {
        if (!cancelled) setEvents(response.events || []);
      })
      .catch(() => {
        if (!cancelled) setEvents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [context.vaultPath, run.run_id, run.updated_at]);

  useEffect(() => {
    setSelectedNode(currentStageKey(run));
  }, [run.flow, run.stage, run.status, run.current_item]);

  async function recoverRun() {
    try {
      const response = await rerunFailedRun(context.vaultPath, run.run_id, {
        config_path: context.configPath,
      });
      context.setNotice({ message: context.t("rerunStarted") });
      await context.loadVaultState(context.vaultPath);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      context.setNotice({ message, error: true });
    }
  }
  return (
    <div className="run-monitor-item run-monitor-card">
      <div className={`run-status-banner ${run.status}`}>
        <div className="run-status-main">
          <span className={runStatusClass(run.status)} />
          <div>
            <strong>{context.t(run.flow)}</strong>
            <p>{run.message || run.stage}</p>
          </div>
        </div>
        <div className="run-status-meta">
          <span>{runStatusLabel(run.status, context.t)}</span>
          <code>{run.run_id}</code>
        </div>
      </div>

      <div className="run-monitor-content">
        <div className="run-monitor-primary">
          <dl className="run-summary-strip">
            <div>
              <dt>{context.t("currentSource")}</dt>
              <dd>
                <RunSourceBadge info={currentSourceInfo(run, events, context.t)} />
              </dd>
            </div>
            <div>
              <dt>{context.t("stage")}</dt>
              <dd>{currentStageLabel(run, context.t)}</dd>
            </div>
            <div>
              <dt>{context.t("elapsed")}</dt>
              <dd>{Math.round(run.elapsed_seconds)}s</dd>
            </div>
            <div>
              <dt>{context.t("lastHeartbeat")}</dt>
              <dd className={staleSeconds > 30 ? "warning-text" : ""}>{staleSeconds}s</dd>
            </div>
            <div>
              <dt>{context.t("progress")}</dt>
              <dd>{percent !== undefined ? `${percent}%` : context.t("notAvailable")}</dd>
            </div>
          </dl>

          <RunStageTrack context={context} events={events} onSelect={setSelectedNode} run={run} selectedNode={selectedNode} />
        {percent !== undefined && (
          <div className="progress-track">
            <span style={{ width: `${percent}%` }} />
          </div>
        )}

          <RunNodeDetails context={context} events={events} run={run} selectedNode={selectedNode} />
        </div>

        <aside className="run-monitor-sidebar">
          <RunSummaryBox context={context} run={run} />
          <div className="run-monitor-actions">
            {reportPath && (
              <button className="button secondary" onClick={() => context.openReport(reportPath)}>
                {context.t("viewReport")}
              </button>
            )}
            {canRecover && (
              <button className="button secondary" onClick={() => void recoverRun()}>
                {context.t("rerunFailed")}
              </button>
            )}
            {run.status !== "failed" && run.status !== "completed" && run.status !== "cancelled" && run.status !== "partially_failed" && (
              <button className="button secondary" onClick={() => void cancelRun(context.vaultPath, run.run_id).then(() => context.loadVaultState(context.vaultPath))}>
                {context.t("cancel")}
              </button>
            )}
          </div>
        <RunErrorBox context={context} run={run} />
        {canRecover && (
          <div className="run-recovery-box">
            <strong>{context.t("recoveryAvailable")}</strong>
            <span>{context.t("recoveryAvailableCopy")}</span>
            {!!recoveryFacts.length && (
              <ul>
                {recoveryFacts.map((fact) => (
                  <li key={fact}>{fact}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        </aside>
      </div>
    </div>
  );
}

function RunSummaryBox({ context, run }: { context: AppContext; run: RunRecord }) {
  const metrics = asRecord(run.metrics);
  const stats = asRecord(run.result_summary?.stats);
  const semanticCalls = numberValue(metrics.semantic_call_count) ?? numberValue(asRecord(metrics.semantic).semantic_call_count);
  const totalTokens = numberValue(metrics.total_tokens) ?? numberValue(asRecord(metrics.semantic).total_tokens);
  const writtenPages = writtenPageCount(run.result_summary?.written_pages) ?? numberValue(stats.written_count);
  const reportPath = reportPathForRun(run);
  const items = [
    { label: "semanticCallsShort", value: semanticCalls },
    { label: "totalTokensShort", value: totalTokens },
    { label: "writtenPagesShort", value: writtenPages },
  ].filter((item) => item.value !== undefined);
  return (
    <div className="run-summary-box">
      <h3>{context.t("runSummary")}</h3>
      {items.length ? (
        <dl>
          {items.map((item) => (
            <div key={item.label}>
              <dt>{context.t(item.label)}</dt>
              <dd>{Number(item.value).toLocaleString()}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>{context.t("noData")}</p>
      )}
      <small>{reportPath ? reportPath : context.t("noReportYet")}</small>
    </div>
  );
}

function RunNodeDetails({ context, events, run, selectedNode }: { context: AppContext; events: RunEvent[]; run: RunRecord; selectedNode: string }) {
  const nodes = flowStages(run.flow);
  const node = nodes.find((item) => item.key === selectedNode) || nodes[0];
  const nodeEvents = events.filter((event) => eventNodeKey(event, run.flow) === node.key).slice(-8);
  const fallbackMessage = node.key === currentStageKey(run) ? run.message || run.stage : context.t("noNodeEvents");
  const resultItems = node.key === "done" ? runResultItems(run, context.t) : [];
  return (
    <section className="run-node-details">
      <div className="run-node-details-header">
        <div>
          <h3>{context.t("nodeDetails")}</h3>
          <p>{context.t(node.label)}</p>
        </div>
        <span>{node.kind === "agent" ? context.t("agentNode") : context.t("workflowNode")}</span>
      </div>
      {resultItems.length ? (
        <dl className="run-node-result">
          {resultItems.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : nodeEvents.length ? (
        <div className="run-node-events">
          {nodeEvents.map((event) => (
            <article className="run-node-event" key={`${event.run_id}:${event.sequence}`}>
              <span className={event.status === "failed" || event.status === "partially_failed" ? "danger" : event.status === "completed" ? "success" : ""} />
              <div>
                <strong>{event.message || event.event_type}</strong>
                <small>
                  {stageLabel(event, context.t)} · {event.created_at}
                </small>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="panel-copy">{fallbackMessage}</p>
      )}
    </section>
  );
}

function RunStageTrack({
  context,
  events,
  onSelect,
  run,
  selectedNode,
}: {
  context: AppContext;
  events: RunEvent[];
  onSelect: (node: string) => void;
  run: RunRecord;
  selectedNode: string;
}) {
  const stages = flowStages(run.flow);
  const current = currentStageKey(run);
  const currentIndex = stages.findIndex((stage) => stage.key === current);
  const metrics = runStageMetrics(run);
  const eventCounts = new Map<string, number>();
  for (const event of events) {
    const key = eventNodeKey(event, run.flow);
    eventCounts.set(key, (eventCounts.get(key) || 0) + 1);
  }
  return (
    <div className="run-stage-track" aria-label={context.t("runStageTrack")}>
      <div className="run-stage-steps">
        {stages.map((stage, index) => {
          const active = stage.key === current;
          const done = currentIndex >= 0 && index < currentIndex;
          return (
            <button
              className={`run-stage-step ${active ? "active" : ""} ${done ? "done" : ""} ${selectedNode === stage.key ? "selected" : ""} ${stage.kind === "agent" ? "agent" : ""}`}
              key={stage.key}
              onClick={() => onSelect(stage.key)}
              title={context.t(stage.label)}
              type="button"
            >
              <span />
              <small>{context.t(stage.label)}</small>
              {!!eventCounts.get(stage.key) && <em>{eventCounts.get(stage.key)}</em>}
            </button>
          );
        })}
      </div>
      {!!metrics.length && (
        <div className="run-stage-metrics">
          {metrics.map((metric) => (
            <span key={metric.label}>
              {context.t(metric.label)}: {metric.value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

type FlowNode = {
  key: string;
  label: string;
  kind?: "workflow" | "agent";
};

function flowStages(flow: RunRecord["flow"]): FlowNode[] {
  if (flow === "lint") {
    return [
      { key: "queued", label: "runStageQueued", kind: "workflow" },
      { key: "scan", label: "runStageScan", kind: "workflow" },
      { key: "diagnose_agent", label: "runStageDiagnoseAgent", kind: "agent" },
      { key: "review_agent", label: "runStageReviewAgent", kind: "agent" },
      { key: "write", label: "runStageWrite", kind: "workflow" },
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
    { key: "retrieval", label: "runStageRetrieval", kind: "workflow" },
    { key: "normalize_agent", label: "runStageNormalizeAgent", kind: "agent" },
    { key: "relation_agent", label: "runStageRelationAgent", kind: "agent" },
    { key: "draft_agent", label: "runStageDraftAgent", kind: "agent" },
    { key: "review_agent", label: "runStageReviewAgent", kind: "agent" },
    { key: "write", label: "runStageWrite", kind: "workflow" },
    { key: "done", label: "runStageDone", kind: "workflow" },
  ];
}

function currentStageKey(run: RunRecord): string {
  if (run.status === "completed" || run.status === "cancelled") return "done";
  if (run.status === "queued" || run.stage === "queued") return "queued";
  const stage = `${run.stage || ""} ${run.current_item || ""}`;
  if (stage.includes("source_normalize")) return "normalize_agent";
  if (stage.includes("wiki_relation")) return "relation_agent";
  if (stage.includes("wiki_draft_compile")) return "draft_agent";
  if (stage.includes("ingest_draft_review")) return "review_agent";
  if (stage.includes("retrieval") || stage.includes("query")) return "retrieval";
  if (run.status === "waiting_model" || stage.includes("semantic") || stage.includes("model") || stage.includes("relation") || stage.includes("draft")) return run.flow === "ingest" ? "review_agent" : "diagnose_agent";
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

function eventNodeKey(event: RunEvent, flow: RunRecord["flow"]): string {
  const text = `${event.stage || ""} ${event.current_item || ""} ${event.message || ""} ${event.event_type || ""}`.toLowerCase();
  if (event.status === "completed") return "done";
  if (text.includes("source_normalize")) return "normalize_agent";
  if (text.includes("wiki_relation")) return "relation_agent";
  if (text.includes("wiki_draft_compile")) return "draft_agent";
  if (text.includes("ingest_draft_review")) return "review_agent";
  if (text.includes("lint_diagnose") || text.includes("quality_diagnose") || text.includes("diagnose")) return "diagnose_agent";
  if (text.includes("review")) return "review_agent";
  if (text.includes("query returned") || text.includes("retrieval") || text.includes("candidate") || text.includes("search")) return flow === "query" ? "search" : "retrieval";
  if (text.includes("segment")) return "segment";
  if (text.includes("standardizing") || text.includes("normalizing") || text.includes("document") || text.includes("preprocess")) return "input";
  if (text.includes("write") || text.includes("report") || text.includes("checkpoint")) return "write";
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

function runStageMetrics(run: RunRecord): Array<{ label: string; value: string }> {
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

type RunSourceInfo = {
  label: string;
  detail?: string;
};

function RunSourceBadge({ info }: { info: RunSourceInfo }) {
  return (
    <span className="run-source-name" title={info.detail ? `${info.label}: ${info.detail}` : info.label}>
      {info.detail || info.label}
    </span>
  );
}

function currentSourceInfo(run: RunRecord, events: RunEvent[], t: (key: string) => string): RunSourceInfo {
  const sourceEvents = events
    .slice()
    .reverse()
    .filter((event) => SOURCE_EVENT_TYPES.has(event.event_type) && typeof event.current_item === "string" && event.current_item.trim());
  const item = sourceEvents[0]?.current_item || sourceFromRunMetadata(run);
  if (!item) return { label: t("notAvailable") };
  return sourceInfoFromValue(item, t);
}

const SOURCE_EVENT_TYPES = new Set(["source_started", "source_processing", "segments_created", "source_queued"]);

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

function runResultItems(run: RunRecord, t: (key: string) => string): Array<{ label: string; value: string }> {
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

function RunErrorBox({ context, run }: { context: AppContext; run: RunRecord }) {
  if (!hasRunErrorInfo(run) || !run.error_info) return null;
  return (
    <div className="run-error-box">
      <strong>{run.error_info.code || context.t("error")}</strong>
      <span>{run.error_info.message || run.error}</span>
      {run.error_info.hint && <small>{run.error_info.hint}</small>}
    </div>
  );
}

function hasRunErrorInfo(run: RunRecord) {
  const info = run.error_info;
  if (!info) return false;
  return Boolean(info.code || info.message || info.hint || info.error_type || run.error);
}

function ingestRecoveryFacts(run: RunRecord, t: (key: string) => string) {
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

function canRecoverRun(run: RunRecord) {
  const recovery = asRecord(run.result_summary?.recovery);
  return run.flow === "ingest" && recovery.available === true;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function writtenPageCount(value: unknown): number | undefined {
  if (typeof value === "number") return value;
  if (Array.isArray(value)) return value.length;
  return undefined;
}

function reportPathForRun(run: RunRecord): string | null {
  const path = run.result_summary?.report_path;
  return typeof path === "string" && path ? path : null;
}

function stageLabel(run: { stage?: string | null; status?: string | null; current_item?: string | null }, t: (key: string) => string): string {
  const stage = run.stage || "";
  const label = displayStageLabel(stage || run.status || "", t);
  const current = run.current_item;
  return current ? `${label} · ${t("currentItem")}: ${current}` : label;
}

function displayStageLabel(stage: string, t: (key: string) => string): string {
  if (!stage) return t("notAvailable");
  const normalized = stage.toLowerCase();
  const statusKey = `runStatus.${normalized}`;
  const statusLabel = t(statusKey);
  if (statusLabel !== statusKey) return statusLabel;
  if (normalized === "queued") return t("runStageQueued");
  if (normalized.includes("segment")) return t("runStageSegment");
  if (normalized.includes("semantic") || normalized.includes("model") || normalized.includes("relation") || normalized.includes("draft")) return t("runStageModel");
  if (normalized.includes("document") || normalized.includes("preprocess") || normalized.includes("normalizing")) return t("runStageInput");
  if (normalized.includes("scan") || normalized.includes("quality")) return t("runStageScan");
  if (normalized.includes("write") || normalized.includes("report") || normalized.includes("checkpoint")) return t("runStageWrite");
  if (normalized.includes("pack") || normalized.includes("context")) return t("runStagePack");
  if (normalized.includes("search") || normalized.includes("query")) return t("runStageSearch");
  return stage.replace(/_/g, " ");
}

function currentStageLabel(run: RunRecord, t: (key: string) => string): string {
  const current = currentStageKey(run);
  const node = flowStages(run.flow).find((stage) => stage.key === current);
  return node ? t(node.label) : displayStageLabel(run.stage || run.status, t);
}

export function RunFlowGuide({ context, mode }: { context: AppContext; mode: "both" | "ingest" | "lint" }) {
  const cards =
    mode === "lint"
      ? [
          { icon: "lint" as const, title: context.t("lintFlowCheck"), copy: context.t("lintFlowCheckCopy") },
          { icon: "reports" as const, title: context.t("lintFlowReview"), copy: context.t("lintFlowReviewCopy") },
        ]
      : mode === "ingest"
        ? [
            { icon: "sources" as const, title: context.t("ingestFlowInput"), copy: context.t("ingestFlowInputCopy") },
            { icon: "mineru" as const, title: context.t("ingestFlowPreprocess"), copy: context.t("ingestFlowPreprocessCopy") },
            { icon: "ingest" as const, title: context.t("ingestFlowCompile"), copy: context.t("ingestFlowCompileCopy") },
          ]
        : [
            { icon: "sources" as const, title: context.t("ingestFlowInput"), copy: context.t("ingestFlowInputCopy") },
            { icon: "ingest" as const, title: context.t("ingestFlowCompile"), copy: context.t("ingestFlowCompileCopy") },
            { icon: "lint" as const, title: context.t("lintFlowCheck"), copy: context.t("lintFlowCheckCopy") },
          ];
  return (
    <article className="run-flow-guide">
      <div className="run-flow-heading">
        <h2>{context.t("processingFlow")}</h2>
        <p>{context.t(mode === "lint" ? "lintProcessingFlowCopy" : "ingestProcessingFlowCopy")}</p>
      </div>
      <div className="run-flow-steps">
        {cards.map((card) => (
          <div className="flow-step-card" key={card.title}>
            <span className="flow-step-icon">
              <LineIcon name={card.icon} />
            </span>
            <div>
              <strong>{card.title}</strong>
              <p>{card.copy}</p>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

export function RunPreflight({ context }: { context: AppContext }) {
  const report = context.doctorReport;
  const diagnostics = context.summary.diagnostics;
  const enabledConnectors = context.summary.enabled_connectors || [];
  const blockingChecks = (report?.checks || []).filter((check) => check.status === "error");
  const warningChecks = (report?.checks || []).filter((check) => check.status === "warning");
  const connectorProblems = [...(diagnostics?.connectors || []), ...(diagnostics?.processors || [])].filter((item) => item.enabled && !item.ok);
  const ready = context.configExists && report?.status !== "error";
  return (
    <article className="panel preflight-panel">
      <div className="panel-header compact">
        <div>
          <h2>{context.t("preflightCheck")}</h2>
          <p className="panel-copy">{context.t("preflightCopy")}</p>
        </div>
        <span className={`pill ${ready ? "success" : report?.status === "warning" ? "" : "danger"}`}>
          {context.configExists ? (report ? context.t(`doctorStatus.${report.status}`) : context.t("configReady")) : context.t("configMissing")}
        </span>
      </div>
      <dl className="runtime-card preflight-card">
        <div>
          <dt>{context.t("configFile")}</dt>
          <dd>{context.configPath || context.t("notConfigured")}</dd>
        </div>
        <div>
          <dt>{context.t("vault")}</dt>
          <dd>{context.vaultPath}</dd>
        </div>
        <div>
          <dt>{context.t("defaultProvider")}</dt>
          <dd>{context.summary.default_provider || context.t("notConfigured")}</dd>
        </div>
        <div>
          <dt>{context.t("enabledConnectors")}</dt>
          <dd>{enabledConnectors.length ? enabledConnectors.join(", ") : context.t("notConfigured")}</dd>
        </div>
        <div>
          <dt>{context.t("doctorChecks")}</dt>
          <dd>{report ? `${report.summary.ok || 0} OK · ${report.summary.warning || 0} ${context.t("warnings")} · ${report.summary.error || 0} ${context.t("errors")}` : context.t("unknown")}</dd>
        </div>
      </dl>
      {!!blockingChecks.length && (
        <ul className="preflight-list error">
          {blockingChecks.slice(0, 4).map((check) => (
            <li key={check.name}>
              <strong>{check.name}</strong>
              <span>{check.message}</span>
            </li>
          ))}
        </ul>
      )}
      {!!warningChecks.length && !blockingChecks.length && (
        <ul className="preflight-list">
          {warningChecks.slice(0, 4).map((check) => (
            <li key={check.name}>
              <strong>{check.name}</strong>
              <span>{check.message}</span>
            </li>
          ))}
        </ul>
      )}
      {!!connectorProblems.length && !report && (
        <p className="panel-copy warning">
          {context.t("preflightWarning")}: {connectorProblems.map((item) => item.name).join(", ")}
        </p>
      )}
    </article>
  );
}
