import type { AppContext } from "../App";
import { LineIcon, type IconName } from "../components/LineIcon";
import { MetricCard } from "../components/MetricCard";
import type { ViewName } from "../types";
import { ActiveRunsPanel } from "../components/runs/RunPanels";

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
      <div className="hero-panel">
        <div>
          <p className="eyebrow">KnoArbor Core</p>
          <h2>{context.t("overviewSubtitle")}</h2>
        </div>
      </div>

      <div className="metric-grid">
        <MetricCard tone="teal" label={context.t("service")} value={context.serviceOnline === true ? context.t("online") : context.serviceOnline === false ? context.t("offline") : context.t("unknown")} hint={context.healthHint} />
        <MetricCard tone={context.doctorReport?.status === "error" ? "rose" : context.doctorReport?.status === "warning" ? "amber" : "teal"} label={context.t("doctorStatus")} value={context.doctorReport ? context.t(`doctorStatus.${context.doctorReport.status}`) : context.t("unknown")} hint={context.t("doctorStatusHint")} />
        <MetricCard tone="blue" label={context.t("pages")} value={context.status?.pages ?? "--"} hint={context.t("maintainedPages")} />
        <MetricCard tone="amber" label={context.t("sources")} value={context.status?.raw_sources ?? "--"} hint={context.t("rawSourceFiles")} />
        <MetricCard tone="rose" label={context.t("lintIssues")} value={context.status?.issues ?? "--"} hint={context.t("deterministicScan")} />
        <MetricCard tone="violet" label={context.t("graphEdges")} value={context.graph?.stats.edge_count ?? "--"} hint={context.t("resolvedWikilinks")} />
      </div>

      <article className="panel next-steps-panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("nextSteps")}</h2>
            <p className="panel-copy">{context.t("nextStepsCopy")}</p>
          </div>
        </div>
        <div className="next-step-grid">
          {nextSteps.map((step) => (
            <button className="next-step-card" key={step.view} onClick={() => onNavigate(step.view)} type="button">
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
      </article>

      <div className="panel-grid dashboard-grid">
        <ActiveRunsPanel context={context} />
        <DoctorSummaryPanel context={context} onNavigate={onNavigate} />
      </div>
    </section>
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

function DoctorSummaryPanel({ context, onNavigate }: Props) {
  const report = context.doctorReport;
  const notable = (report?.checks || []).filter((check) => check.status !== "ok").slice(0, 4);
  return (
    <article className={`panel doctor-panel ${report?.status || "unknown"}`}>
      <div className="panel-header">
        <div>
          <h2>{context.t("doctorPanelTitle")}</h2>
          <p className="panel-copy">{context.t("doctorPanelCopy")}</p>
        </div>
        <span className={`pill ${report?.status === "ok" ? "success" : report?.status === "error" ? "danger" : ""}`}>
          {report ? context.t(`doctorStatus.${report.status}`) : context.t("unknown")}
        </span>
      </div>
      {report ? (
        <>
          <div className="doctor-counts">
            <span>{context.t("doctorOk")}: {report.summary.ok || 0}</span>
            <span>{context.t("doctorWarning")}: {report.summary.warning || 0}</span>
            <span>{context.t("doctorError")}: {report.summary.error || 0}</span>
          </div>
          {notable.length ? (
            <ul className="doctor-list">
              {notable.map((check) => (
                <li key={check.name}>
                  <strong>{check.name}</strong>
                  <span>{check.message}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="panel-copy">{context.t("doctorAllClear")}</p>
          )}
        </>
      ) : (
        <p className="panel-copy">{context.t("doctorUnavailable")}</p>
      )}
      <button className="button secondary" onClick={() => onNavigate("settings")} type="button">
        {context.t("openSettings")}
      </button>
    </article>
  );
}
