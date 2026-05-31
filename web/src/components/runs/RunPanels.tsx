import { cancelRun, rerunFailedRun } from "../../api/client";
import type { AppContext } from "../../App";
import { LineIcon } from "../LineIcon";
import { runStatusClass, runStatusLabel } from "../runStatus";
import type { RunRecord } from "../../types";

export function ActiveRunsPanel({ context, includeRecoverable = false }: { context: AppContext; includeRecoverable?: boolean }) {
  const recoverableRecent = context.recentRuns.filter(
    (run) => run.flow === "ingest" && (run.status === "failed" || run.status === "partially_failed"),
  );
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
  const canRecover = run.flow === "ingest" && (run.status === "failed" || run.status === "partially_failed");
  const recoveryFacts = ingestRecoveryFacts(run, context.t);
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
    <div className="run-monitor-item">
      <div>
        <div className="run-monitor-title">
          <span className={runStatusClass(run.status)} />
          <strong>{context.t(run.flow)}</strong>
          <span>{runStatusLabel(run.status, context.t)}</span>
          <code>{run.run_id}</code>
        </div>
        <p>{run.message || run.stage}</p>
        <small>
          {context.t("stage")}: {run.stage}
          {run.current_item ? ` · ${context.t("currentItem")}: ${run.current_item}` : ""}
          {` · ${context.t("lastHeartbeat")}: ${staleSeconds}s`}
        </small>
        <div className="run-monitor-chips">
          <span>{context.t("elapsed")}: {Math.round(run.elapsed_seconds)}s</span>
          {percent !== undefined && <span>{context.t("progress")}: {percent}%</span>}
          {staleSeconds > 30 && <span className="warning-chip">{context.t("heartbeatStale")}</span>}
        </div>
        {percent !== undefined && (
          <div className="progress-track">
            <span style={{ width: `${percent}%` }} />
          </div>
        )}
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
      </div>
      <div className="run-monitor-actions">
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
    </div>
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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
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
