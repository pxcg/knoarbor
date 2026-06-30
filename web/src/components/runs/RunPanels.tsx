import { useEffect, useState } from "react";

import { cancelRun, getRunEvents, rerunFailedRun } from "../../api/client";
import type { AppContext } from "../../appContext";
import { LineIcon } from "../LineIcon";
import { runStatusClass, runStatusLabel } from "../runStatus";
import type { RunEvent, RunRecord } from "../../types";
import {
  asRecord,
  canRecoverRun,
  currentSourceInfo,
  currentStageKey,
  currentStageLabel,
  dedupeRuns,
  eventNodeKey,
  flowStages,
  ingestRecoveryFacts,
  numberValue,
  reportPathForRun,
  runResultItems,
  runStageMetrics,
  stageLabel,
  writtenPageCount,
  type RunSourceInfo,
} from "./RunPanelModel";

export function ActiveRunsPanel({ context, includeRecoverable = false }: { context: AppContext; includeRecoverable?: boolean }) {
  const recoverableRecent = context.recentRuns.filter((run) => canRecoverRun(run));
  const runs = dedupeRuns(context.activeRuns);
  if (!runs.length) {
    return (
      <>
        <article className="panel run-monitor-panel">
          <div className="panel-header compact">
            <div>
              <h2>{context.t("runMonitor")}</h2>
              <p className="panel-copy">{context.t("noActiveRuns")}</p>
            </div>
          </div>
          <RunFlowPlaceholder context={context} />
        </article>
        {includeRecoverable && recoverableRecent.length ? <RecoverableRunsPanel context={context} runs={recoverableRecent.slice(0, 4)} /> : null}
      </>
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

function RecoverableRunsPanel({ context, runs }: { context: AppContext; runs: RunRecord[] }) {
  async function recoverRun(runId: string) {
    try {
      await rerunFailedRun(context.activeVaultSelector, runId, {
        config_path: context.configPath,
      });
      context.setNotice({ message: context.t("rerunStarted") });
      await context.loadVaultState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      context.setNotice({ message, error: true });
    }
  }
  return (
    <article className="panel recoverable-run-panel">
      <div className="panel-header">
        <div>
          <h2>{context.t("recoveryAvailable")}</h2>
          <p className="panel-copy">{context.t("recoverableRunsCopy")}</p>
        </div>
      </div>
      <div className="recoverable-run-list">
        {runs.map((run) => {
          const reportPath = reportPathForRun(run);
          return (
            <article className="recoverable-run-card" key={run.run_id}>
              <div>
                <strong>{context.t(run.flow)}</strong>
                <code>{run.run_id}</code>
                <small>
                  {context.t("stage")}: {currentStageLabel(run, context.t)} · {context.t("elapsed")}: {Math.round(run.elapsed_seconds)}s
                </small>
              </div>
              <div>
                {reportPath && (
                  <button className="button secondary small-button" onClick={() => context.openReport(reportPath)} type="button">
                    {context.t("viewReport")}
                  </button>
                )}
                <button className="button secondary small-button" onClick={() => void recoverRun(run.run_id)} type="button">
                  {context.t("rerunFailed")}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </article>
  );
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
    getRunEvents(context.activeVaultSelector, run.run_id)
      .then((response) => {
        if (!cancelled) setEvents(response.events || []);
      })
      .catch(() => {
        if (!cancelled) setEvents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [context.activeVaultSelector, run.run_id, run.updated_at]);

  useEffect(() => {
    setSelectedNode(currentStageKey(run));
  }, [run.flow, run.stage, run.status, run.current_item]);

  async function recoverRun() {
    try {
      const response = await rerunFailedRun(context.activeVaultSelector, run.run_id, {
        config_path: context.configPath,
      });
      context.setNotice({ message: context.t("rerunStarted") });
      await context.loadVaultState();
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
          <RunSummaryBox context={context} events={events} run={run} />
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
              <button className="button secondary" onClick={() => void cancelRun(context.activeVaultSelector, run.run_id).then(() => context.loadVaultState())}>
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

function RunSummaryBox({ context, events, run }: { context: AppContext; events: RunEvent[]; run: RunRecord }) {
  const metrics = asRecord(run.metrics);
  const stats = asRecord(run.result_summary?.stats);
  const semanticCalls = numberValue(metrics.semantic_call_count) ?? numberValue(asRecord(metrics.semantic).semantic_call_count) ?? latestEventNumber(events, ["semantic_call_count", "semantic_calls"]);
  const totalTokens = numberValue(metrics.total_tokens) ?? numberValue(asRecord(metrics.semantic).total_tokens) ?? latestEventNumber(events, ["total_tokens"]);
  const writtenPages = writtenPageCount(run.result_summary?.written_pages) ?? numberValue(stats.written_count) ?? latestEventNumber(events, ["written_pages", "written_count"]);
  const reportPath = reportPathForRun(run);
  const items = [
    { label: context.t("stage"), value: currentStageLabel(run, context.t) },
    { label: context.t("elapsed"), value: `${Math.round(run.elapsed_seconds)}s` },
    { label: context.t("recentEvents"), value: String(events.length) },
    semanticCalls !== undefined ? { label: context.t("semanticCallsShort"), value: semanticCalls.toLocaleString() } : null,
    totalTokens !== undefined ? { label: context.t("totalTokensShort"), value: totalTokens.toLocaleString() } : null,
    writtenPages !== undefined ? { label: context.t("writtenPagesShort"), value: writtenPages.toLocaleString() } : null,
  ].filter((item): item is { label: string; value: string } => Boolean(item));
  return (
    <div className="run-summary-box">
      <h3>{context.t("runSummary")}</h3>
      <dl>
        {items.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
      <small>{reportPath ? reportPath : context.t("noReportYet")}</small>
    </div>
  );
}

function latestEventNumber(events: RunEvent[], keys: string[]): number | undefined {
  for (const event of events.slice().reverse()) {
    const sources = [asRecord(event.metrics), asRecord(asRecord(event.metrics).semantic), asRecord(event.payload)];
    for (const source of sources) {
      for (const key of keys) {
        const value = numberValue(source[key]);
        if (value !== undefined) return value;
      }
    }
  }
  return undefined;
}

function RunFlowPlaceholder({ context }: { context: AppContext }) {
  const stages = flowStages("ingest");
  return (
    <div className="run-flow-placeholder" aria-label={context.t("runStageTrack")}>
      <div className="run-stage-steps">
        {stages.map((stage) => (
          <span className={`run-stage-step placeholder ${stage.kind === "agent" ? "agent" : ""}`} key={stage.key}>
            <span />
            <small>{context.t(stage.label)}</small>
          </span>
        ))}
      </div>
      <div className="run-placeholder-note">{context.t("noRunYet")}</div>
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

function RunSourceBadge({ info }: { info: RunSourceInfo }) {
  return (
    <span className="run-source-name" title={info.detail ? `${info.label}: ${info.detail}` : info.label}>
      {info.detail || info.label}
    </span>
  );
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
      {!!report?.next_steps?.length && (
        <div className="preflight-next-steps">
          <h3>{context.t("doctorNextSteps")}</h3>
          <ul>
            {report.next_steps.slice(0, 5).map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
