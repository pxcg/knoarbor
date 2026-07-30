import { useEffect, useRef, useState } from "react";

import { cancelRun, getRun, getRunEvents, rerunFailedRun } from "../../api/client";
import type { RunAppContext } from "../../appContext";
import type { RunEvent, RunRecord } from "../../types";
import { runStatusClass, runStatusLabel } from "../runStatus";
import { canRecoverRun, currentSourceInfo, currentStageKey, currentStageLabel, eventNodeKey, ingestRecoveryFacts, isMaterializationPending, isTerminalRunStatus, reportPathForRun, runProgressPercent } from "./RunPanelModel";
import { RunErrorBox, RunNodeDetails, RunSourceBadge, RunStageTrack } from "./RunMonitorDetails";
import { userFacingError } from "../../userFacingError";

export function RunMonitorItem({
  context,
  onTerminal,
  run,
}: {
  context: RunAppContext;
  onTerminal?: (run: RunRecord) => void;
  run: RunRecord;
}) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [terminalRun, setTerminalRun] = useState<RunRecord | null>(null);
  const eventCursor = useRef(0);
  const terminalHandled = useRef<string | null>(null);
  const latestEvent = events[events.length - 1];
  const liveRun = terminalRun || (latestEvent ? runFromLatestEvent(run, latestEvent) : run);
  const staleSeconds = Math.max(0, Math.round((Date.now() - Date.parse(liveRun.last_heartbeat_at)) / 1000));
  const canRecover = canRecoverRun(liveRun);
  const recoveryFacts = ingestRecoveryFacts(liveRun, context.t);
  const reportPath = reportPathForRun(liveRun);
  const [selectedNode, setSelectedNode] = useState<string>(() => currentStageKey(run));

  useEffect(() => {
    eventCursor.current = 0;
    terminalHandled.current = null;
    setEvents([]);
    setTerminalRun(null);
  }, [run.run_id]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const active = isActiveRun(run.status);

    async function pollEvents() {
      try {
        const response = await getRunEvents(context.activeVaultSelector, run.run_id, eventCursor.current);
        if (cancelled) return;
        const incoming = response.events || [];
        if (incoming.length) {
          eventCursor.current = Math.max(eventCursor.current, ...incoming.map((event) => event.sequence));
          setEvents((current) => mergeRunEvents(current, incoming));
        }
      } catch (error) {
        console.error("Run event refresh failed", error);
      } finally {
        if (!cancelled && active) timer = window.setTimeout(pollEvents, 1000);
      }
    }

    void pollEvents();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [context.activeVaultSelector, run.run_id, run.status]);

  useEffect(() => {
    setSelectedNode(latestEvent ? eventNodeKey(latestEvent, run.flow) : currentStageKey(run));
  }, [latestEvent, run.flow, run.stage, run.status, run.current_item]);

  useEffect(() => {
    if (!isTerminalRunStatus(liveRun.status)) return;
    const terminalKey = `${liveRun.run_id}:${liveRun.status}`;
    if (terminalHandled.current === terminalKey) return;
    terminalHandled.current = terminalKey;
    let cancelled = false;
    getRun(context.activeVaultSelector, liveRun.run_id)
      .catch(() => liveRun)
      .then((authoritativeRun) => {
        if (cancelled) return;
        const resolvedRun = isTerminalRunStatus(authoritativeRun.status) ? authoritativeRun : liveRun;
        setTerminalRun(resolvedRun);
        void context.refreshAfterRunTerminal(resolvedRun);
        onTerminal?.(resolvedRun);
      });
    return () => {
      cancelled = true;
    };
  }, [context.activeVaultSelector, context.refreshAfterRunTerminal, liveRun.run_id, liveRun.status, onTerminal]);

  const percent = runProgressPercent(liveRun, events);
  const materializationPending = isMaterializationPending(liveRun);

  async function recoverRun() {
    try {
      await rerunFailedRun(context.activeVaultSelector, run.run_id, {
        config_path: context.configPath,
      });
      await context.loadVaultState();
    } catch (error) {
      console.error("Run recovery failed", error);
    }
  }

  return (
    <div className="run-monitor-item run-monitor-card">
      <div className={`run-status-banner ${liveRun.status}`}>
        <div className="run-status-main">
          <span className={runStatusClass(liveRun.status)} />
          <div>
            <strong>{context.t(run.flow)}</strong>
            <p>{isFailedRun(liveRun.status) ? userFacingError(liveRun.error || liveRun.message, context.language) : (liveRun.message || liveRun.stage)}</p>
          </div>
        </div>
        <div className="run-status-meta">
          <span>{runStatusLabel(liveRun.status, context.t)}</span>
          <code>{run.run_id}</code>
        </div>
      </div>
      {materializationPending && (
        <p className="settings-action-note warning" role="alert">
          <strong>{context.t("materializationPendingTitle")}</strong>{" "}
          {context.t("materializationPendingCopy")}
        </p>
      )}

      <div className="run-monitor-content">
        <div className="run-monitor-primary">
          <dl className="run-summary-strip">
            <div>
              <dt>{context.t("currentSource")}</dt>
              <dd>
                <RunSourceBadge info={currentSourceInfo(liveRun, events, context.t)} />
              </dd>
            </div>
            <div>
              <dt>{context.t("stage")}</dt>
              <dd>{currentStageLabel(liveRun, context.t)}</dd>
            </div>
            <div>
              <dt>{context.t("elapsed")}</dt>
              <dd>{Math.round(liveRun.elapsed_seconds)}s</dd>
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

          <RunStageTrack context={context} events={events} onSelect={setSelectedNode} run={liveRun} selectedNode={selectedNode} />
          {percent !== undefined && (
            <div className="progress-track">
              <span style={{ width: `${percent}%` }} />
            </div>
          )}

          <RunNodeDetails context={context} events={events} run={liveRun} selectedNode={selectedNode} />
        </div>

        <aside className="run-monitor-sidebar">
          <div className="run-monitor-actions">
            {reportPath && (
              <button className="button secondary" onClick={() => context.openReport(reportPath, context.activeVaultId)}>
                {context.t("viewReport")}
              </button>
            )}
            {canRecover && (
              <button className="button secondary" onClick={() => void recoverRun()}>
                {context.t("rerunFailed")}
              </button>
            )}
            {isActiveRun(liveRun.status) && (
              <button className="button secondary danger-outline" onClick={() => void cancelRun(context.activeVaultSelector, run.run_id).then(() => context.loadVaultState())}>
                {context.t("cancel")}
              </button>
            )}
          </div>
          <RunErrorBox context={context} run={liveRun} />
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

function isFailedRun(status: string) {
  return ["failed", "partially_failed", "recovery_needed", "paused_rate_limited"].includes(status);
}

function isActiveRun(status: RunRecord["status"]) {
  return !isTerminalRunStatus(status);
}

function mergeRunEvents(current: RunEvent[], incoming: RunEvent[]) {
  const bySequence = new Map(current.map((event) => [event.sequence, event]));
  for (const event of incoming) bySequence.set(event.sequence, event);
  return Array.from(bySequence.values()).sort((left, right) => left.sequence - right.sequence);
}

function runFromLatestEvent(run: RunRecord, event: RunEvent): RunRecord {
  const active = isActiveRun(event.status);
  return {
    ...run,
    status: event.status,
    stage: event.stage || run.stage,
    current_item: event.current_item ?? run.current_item,
    message: event.message || run.message,
    progress: event.progress || run.progress,
    metrics: { ...run.metrics, ...event.metrics },
    updated_at: event.created_at,
    last_heartbeat_at: run.last_heartbeat_at,
    elapsed_seconds: active
      ? Math.max(run.elapsed_seconds, (Date.now() - Date.parse(run.started_at)) / 1000)
      : run.elapsed_seconds,
  };
}
