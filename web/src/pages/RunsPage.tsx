import { useMemo } from "react";

import type { AppContext } from "../appContext";
import { runStatusClass, runStatusLabel } from "../components/runStatus";
import { ActiveRunsPanel } from "../components/runs/RunPanels";
import type { RunRecord } from "../types";

type Props = {
  context: AppContext;
};

export function RunsPage({ context }: Props) {
  const recentRuns = useMemo(() => {
    const runs = context.vaultOverviews.length > 1 ? context.vaultOverviews.flatMap((item) => item.recentRuns) : context.recentRuns;
    return [...runs].sort((left, right) => String(right.updated_at || "").localeCompare(String(left.updated_at || ""))).slice(0, 12);
  }, [context.recentRuns, context.vaultOverviews]);
  const groupedRuns = useMemo(() => groupRunsByVault(recentRuns, context), [context, recentRuns]);

  return (
    <section className="view active">
      <ActiveRunsPanel context={context} includeRecoverable />
      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("recentRuns")}</h2>
            <p className="panel-copy">{context.t("recentRunsCopy")}</p>
          </div>
        </div>
        <div className="run-history-list">
          {recentRuns.length ? (
            groupedRuns.map((group) => (
              <section className="vault-list-group" key={group.key}>
                {context.vaultOptions.length > 1 && (
                  <header>
                    <strong>{group.label}</strong>
                    <span>{group.runs.length} {context.t("recentRuns")}</span>
                  </header>
                )}
                {group.runs.map((run) => {
                  const reportPath = reportPathForRun(run);
                  return (
                    <button
                      className={`run-history-item ${reportPath ? "clickable" : ""}`}
                      disabled={!reportPath}
                      key={`${run.vault_id || run.vault_path || "vault"}:${run.run_id}`}
                      onClick={() => reportPath && openRunReport(context, run, reportPath)}
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
                })}
              </section>
            ))
          ) : (
          <div className="empty-state">{context.t("noRunYet")}</div>
          )}
        </div>
      </article>
      <VaultRunsSummary context={context} />
    </section>
  );
}

function VaultRunsSummary({ context }: { context: AppContext }) {
  if (context.vaultOverviews.length <= 1) return null;
  return (
    <details className="panel vault-runs-panel compact-vault-overview">
      <summary>
        <span>{context.t("allVaults")}</span>
        <small>{context.t("vaultOverviewCopy")}</small>
      </summary>
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
    </details>
  );
}

function reportPathForRun(run: { result_summary: Record<string, unknown> }) {
  const path = run.result_summary?.report_path;
  return typeof path === "string" && path ? path : null;
}

function openRunReport(context: AppContext, run: RunRecord, reportPath: string) {
  if (run.vault_id) context.setActiveVaultId(run.vault_id);
  context.openReport(reportPath);
}

function groupRunsByVault(runs: RunRecord[], context: AppContext) {
  const groups = new Map<string, { key: string; label: string; runs: RunRecord[] }>();
  for (const run of runs) {
    const vault =
      (run.vault_id ? context.vaultOptions.find((item) => item.id === run.vault_id) : null) ||
      (run.vault_path ? context.vaultOptions.find((item) => item.path === run.vault_path) : null);
    const key = vault?.id || run.vault_id || run.vault_path || "vault";
    const group = groups.get(key) || { key, label: vault?.name || run.vault_name || run.vault_id || key, runs: [] };
    group.runs.push(run);
    groups.set(key, group);
  }
  return Array.from(groups.values());
}
