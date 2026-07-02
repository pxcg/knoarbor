import { useEffect, useState } from "react";

import { cancelRun, getRunEvents, rerunFailedRun } from "../../api/client";
import type { AppContext } from "../../appContext";
import type { RunEvent, RunRecord } from "../../types";
import { runStatusClass, runStatusLabel } from "../runStatus";
import { canRecoverRun, currentSourceInfo, currentStageKey, currentStageLabel, ingestRecoveryFacts, reportPathForRun } from "./RunPanelModel";
import { RunErrorBox, RunNodeDetails, RunSourceBadge, RunStageTrack, RunSummaryBox } from "./RunMonitorDetails";

export function RunMonitorItem({ context, run }: { context: AppContext; run: RunRecord }) {
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
      await rerunFailedRun(context.activeVaultSelector, run.run_id, {
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
