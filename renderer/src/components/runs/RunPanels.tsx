import { rerunFailedRun } from "../../api/client";
import type { RunAppContext } from "../../appContext";
import type { RunRecord } from "../../types";
import { canRecoverRun, currentStageLabel, dedupeRuns, reportPathForRun } from "./RunPanelModel";
import { RunFlowPlaceholder } from "./RunMonitorDetails";
import { RunMonitorItem } from "./RunMonitorItem";

export function ActiveRunsPanel({
  context,
  excludeRunId,
  flow,
  includeRecoverable = false,
}: {
  context: RunAppContext;
  excludeRunId?: string;
  flow?: RunRecord["flow"];
  includeRecoverable?: boolean;
}) {
  const recoverableRecent = context.recentRuns.filter((run) => canRecoverRun(run) && (!flow || run.flow === flow));
  const runs = dedupeRuns(context.activeRuns.filter((run) => (!flow || run.flow === flow) && run.run_id !== excludeRunId));
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
          <RunFlowPlaceholder context={context} flow={flow} />
        </article>
        {includeRecoverable && recoverableRecent.length ? <RecoverableRunsPanel context={context} runs={recoverableRecent} /> : null}
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

function RecoverableRunsPanel({ context, runs }: { context: RunAppContext; runs: RunRecord[] }) {
  async function recoverRun(runId: string) {
    try {
      await rerunFailedRun(context.activeVaultSelector, runId, {
        config_path: context.configPath,
      });
      await context.loadVaultState();
    } catch (error) {
      console.error("Run recovery failed", error);
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
                  <button className="button secondary small-button" onClick={() => context.openReport(reportPath, context.activeVaultId)} type="button">
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
