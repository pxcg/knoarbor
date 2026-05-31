import type { AppContext } from "../App";
import { runStatusClass, runStatusLabel } from "../components/runStatus";
import { ActiveRunsPanel, RunPreflight } from "./RunPage";

type Props = {
  context: AppContext;
};

export function RunsPage({ context }: Props) {
  return (
    <section className="view active">
      <div className="page-intro">
        <div>
          <p className="eyebrow">{context.t("runMonitor")}</p>
          <h2>{context.t("runsTitle")}</h2>
          <p className="panel-copy">{context.t("runsSubtitle")}</p>
        </div>
      </div>
      <RunPreflight context={context} />
      <ActiveRunsPanel context={context} includeRecoverable />
      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("recentRuns")}</h2>
            <p className="panel-copy">{context.t("recentRunsCopy")}</p>
          </div>
        </div>
        <div className="run-history-list">
          {context.recentRuns.length ? (
            context.recentRuns.slice(0, 12).map((run) => {
              const reportPath = reportPathForRun(run);
              return (
                <button
                  className={`run-history-item ${reportPath ? "clickable" : ""}`}
                  disabled={!reportPath}
                  key={run.run_id}
                  onClick={() => reportPath && context.openReport(reportPath)}
                  type="button"
                >
                  <div>
                    <span className={runStatusClass(run.status)} />
                    <strong>{context.t(run.flow)}</strong>
                    <span>{runStatusLabel(run.status, context.t)}</span>
                    <code>{run.run_id}</code>
                  </div>
                  <small>
                    {context.t("stage")}: {run.stage} · {context.t("elapsed")}: {Math.round(run.elapsed_seconds)}s
                  </small>
                </button>
              );
            })
          ) : (
            <div className="empty-state">{context.t("noRunYet")}</div>
          )}
        </div>
      </article>
    </section>
  );
}

function reportPathForRun(run: { result_summary: Record<string, unknown> }) {
  const path = run.result_summary?.report_path;
  return typeof path === "string" && path ? path : null;
}
