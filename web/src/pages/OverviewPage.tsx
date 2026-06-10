import type { AppContext } from "../App";
import { LineIcon, type IconName } from "../components/LineIcon";
import { MetricCard } from "../components/MetricCard";
import type { ViewName } from "../types";

type Props = {
  context: AppContext;
  onNavigate: (view: ViewName) => void;
};

type NextStep = {
  view: ViewName;
  titleKey: string;
  copyKey: string;
  icon: IconName;
  tone: string;
};

export function OverviewPage({ context, onNavigate }: Props) {
  const nextSteps = buildNextSteps(context);
  return (
    <section className="view active">
      <div className="hero-panel overview-hero">
        <div className="overview-hero-copy">
          <p className="eyebrow">KnoArbor</p>
          <h2>{context.t("overviewSubtitle")}</h2>
          <p>{context.t("overviewHeroCopy")}</p>
        </div>
      </div>

      <div className="metric-grid overview-metric-grid">
        <MetricCard tone="blue" label={context.t("pages")} value={context.status?.pages ?? "--"} hint={context.t("maintainedPages")} />
        <MetricCard tone="amber" label={context.t("sources")} value={context.status?.raw_sources ?? "--"} hint={context.t("rawSourceFiles")} />
        <MetricCard tone="rose" label={context.t("lintIssues")} value={context.status?.issues ?? "--"} hint={context.t("deterministicScan")} />
        <MetricCard tone="violet" label={context.t("graphEdges")} value={context.graph?.stats.edge_count ?? "--"} hint={context.t("resolvedWikilinks")} />
      </div>

      <VaultOverviewPanel context={context} />

      <article className="panel next-steps-panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("nextSteps")}</h2>
            <p className="panel-copy">{context.t("nextStepsCopy")}</p>
          </div>
        </div>
        <div className="next-step-grid">
          {nextSteps.map((step) => (
            <button className="next-step-card" key={step.view} onClick={() => (step.view === "settings" ? context.openSettings() : onNavigate(step.view))} type="button">
              <span className={`next-step-icon tone-${step.tone}`} aria-hidden="true">
                <LineIcon name={step.icon} />
              </span>
              <span className="next-step-body">
                <strong>{context.t(step.titleKey)}</strong>
                <span>{context.t(step.copyKey)}</span>
              </span>
            </button>
          ))}
        </div>
        {!!context.doctorReport?.next_steps?.length && (
          <div className="doctor-next-steps">
            <h3>{context.t("doctorNextSteps")}</h3>
            <ul>
              {context.doctorReport.next_steps.slice(0, 4).map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>
        )}
      </article>
    </section>
  );
}

function VaultOverviewPanel({ context }: { context: AppContext }) {
  return (
    <article className="panel vault-overview-panel">
      <div className="panel-header">
        <div>
          <h2>{context.t("vaultOverview")}</h2>
          <p className="panel-copy">{context.t("vaultOverviewCopy")}</p>
        </div>
        <span className="pill">{`${context.vaultOverviews.length} ${context.t("allVaults")}`}</span>
      </div>
      <div className="vault-overview-grid">
        {context.vaultOverviews.map((item) => (
          <button
            className={`vault-overview-card ${item.vault.id === context.activeVaultId ? "active" : ""}`}
            key={item.vault.id}
            onClick={() => context.setActiveVaultId(item.vault.id)}
            type="button"
          >
            <span className="vault-card-head">
              <strong>{item.vault.name}</strong>
              {item.vault.id === context.activeVaultId && <em>{context.t("activeVault")}</em>}
            </span>
            <code>{item.vault.path}</code>
            {item.error ? (
              <small className="danger-text">{item.error}</small>
            ) : (
              <span className="vault-card-metrics">
                <span>{context.t("pages")}: {item.status?.pages ?? "--"}</span>
                <span>{context.t("lintIssues")}: {item.status?.issues ?? "--"}</span>
                <span>{context.t("activeRuns")}: {item.activeRuns.length}</span>
                <span>{context.t("reports")}: {item.reports.length}</span>
              </span>
            )}
          </button>
        ))}
      </div>
    </article>
  );
}

function buildNextSteps(context: AppContext): NextStep[] {
  const steps: NextStep[] = [];
  const add = (step: NextStep) => {
    if (!steps.some((item) => item.view === step.view)) steps.push(step);
  };

  if (context.activeRuns.length > 0) {
    add({ view: "runs", titleKey: "nextStepRunningTitle", copyKey: "nextStepRunningCopy", icon: "runs", tone: "emerald" });
  }
  if (context.doctorReport?.status === "error" || context.doctorReport?.status === "warning" || context.serviceOnline === false) {
    add({ view: "settings", titleKey: "nextStepConfigTitle", copyKey: "nextStepConfigCopy", icon: "settings", tone: "amber" });
  }
  if (!context.status || (context.status.pages || 0) === 0) {
    add({ view: "ingest", titleKey: "nextStepIngestTitle", copyKey: "nextStepIngestCopy", icon: "ingest", tone: "teal" });
  }
  if ((context.status?.issues || 0) > 0) {
    add({ view: "lint", titleKey: "nextStepLintTitle", copyKey: "nextStepLintCopy", icon: "lint", tone: "blue" });
  }
  if ((context.status?.pages || 0) > 0) {
    add({ view: "query", titleKey: "nextStepQueryTitle", copyKey: "nextStepQueryCopy", icon: "query", tone: "violet" });
  }
  if (context.reports.length > 0) {
    add({ view: "reports", titleKey: "nextStepReportsTitle", copyKey: "nextStepReportsCopy", icon: "reports", tone: "blue" });
  }
  if (steps.length === 0) {
    add({ view: "sources", titleKey: "nextStepSourcesTitle", copyKey: "nextStepSourcesCopy", icon: "sources", tone: "teal" });
  }
  return steps.slice(0, 3);
}
