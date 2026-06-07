import type { AppContext } from "../App";
import { runStatusClass, runStatusLabel } from "../components/runStatus";
import { ActiveRunsPanel, RunPreflight } from "../components/runs/RunPanels";

type Props = {
  context: AppContext;
};

export function RunsPage({ context }: Props) {
  return (
    <section className="view active">
      <VaultRunsSummary context={context} />
      <ActiveRunsPanel context={context} includeRecoverable />
      <RunPreflight context={context} />
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

function VaultRunsSummary({ context }: { context: AppContext }) {
  if (context.vaultOverviews.length <= 1) return null;
  return (
    <article className="panel vault-runs-panel">
      <div className="panel-header">
        <div>
          <h2>{context.t("allVaults")}</h2>
          <p className="panel-copy">{context.t("vaultOverviewCopy")}</p>
        </div>
      </div>
      <div className="vault-run-grid">
        {context.vaultOverviews.map((item) => (
          <button
            className={`vault-run-card ${item.vault.id === context.activeVaultId ? "active" : ""}`}
            key={item.vault.id}
            onClick={() => context.setActiveVaultId(item.vault.id)}
            type="button"
          >
            <strong>{item.vault.name}</strong>
            <span>{context.t("activeRuns")}: {item.activeRuns.length}</span>
            <span>{context.t("recentRuns")}: {item.recentRuns.length}</span>
            <span>{context.t("reports")}: {item.reports.length}</span>
          </button>
        ))}
      </div>
    </article>
  );
}

function reportPathForRun(run: { result_summary: Record<string, unknown> }) {
  const path = run.result_summary?.report_path;
  return typeof path === "string" && path ? path : null;
}
