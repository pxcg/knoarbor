import type { AppContext } from "../../appContext";

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
