import { useCallback, useEffect, useMemo, useState } from "react";

import { getPage, getReport, getRunEvents, type ReportDetail, type ReportSummary, type VaultSelector } from "../api/client";
import type { ReportsAppContext } from "../appContext";
import { LoadingBlock } from "../components/LoadingBlock";
import { ReportReadableView } from "../components/report/ReportReadableView";
import { ReportSummaryCard } from "../components/report/ReportSummaryCard";
import { parseReportRunId } from "../components/report/reportParser";
import { localizeReportKind, localizeReportLabel, localizeReportTitle } from "../components/reportLabels";
import { runStatusLabel } from "../components/runStatus";
import type { RunEvent } from "../types";
import { userFacingError } from "../userFacingError";

type Props = { active: boolean; context: ReportsAppContext };

export function ReportsPage({ active, context }: Props) {
  const [selected, setSelected] = useState<ReportDetail | null>(null);
  const [selectedRunEvents, setSelectedRunEvents] = useState<RunEvent[]>([]);
  const [loadingReportPath, setLoadingReportPath] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<"ingest" | "lint" | "query">("lint");
  const [navigationError, setNavigationError] = useState<string | null>(null);
  const allReports = useMemo(
    () => [...context.reports].sort((left, right) => String(right.updated || "").localeCompare(String(left.updated || ""))),
    [context.reports],
  );
  const filteredReports = useMemo(
    () => allReports.filter((report) => reportBucket(report.kind) === activeKind),
    [activeKind, allReports],
  );
  const reportOverview = useMemo(
    () =>
      (["ingest", "lint", "query"] as const).map((kind) => {
        const reports = allReports.filter((report) => reportBucket(report.kind) === kind);
        return {
          kind,
          count: reports.length,
          latest: reports[0]?.updated || context.t("unknown"),
        };
      }),
    [allReports, context.t],
  );

  function switchReportKind(kind: "ingest" | "lint" | "query") {
    setActiveKind(kind);
    if (selected && reportBucket(selected.summary.kind) !== kind) {
      setSelected(null);
    }
  }

  const loadReport = useCallback(async (reportSummary: ReportSummary) => {
    setLoadingReportPath(reportKey(reportSummary));
    try {
      const vault = vaultForReport(context, reportSummary);
      const selector = selectorForReport(context, reportSummary, vault);
      const report = await getReport(selector, reportSummary.path);
      setSelected(report);
      setSelectedRunEvents([]);
      const runId = parseReportRunId(report.content);
      if (!runId) {
        return;
      }
      try {
        const events = await getRunEvents(selector, runId);
        setSelectedRunEvents(events.events || []);
      } catch {
        setSelectedRunEvents([]);
      }
    } catch (error) {
      console.error("Report loading failed", error);
    } finally {
      setLoadingReportPath(null);
    }
  }, [context]);

  useEffect(() => {
    if (!active) return;
    const target = context.navigationTarget;
    if (target?.kind !== "report" || target.vaultId !== context.activeVaultId || !context.reportsReady) return;
    const report = allReports.find((item) =>
      item.path === target.path && (item.vault_id === target.vaultId || vaultForReport(context, item).id === target.vaultId),
    );
    if (report) {
      setActiveKind(reportBucket(report.kind));
      setNavigationError(null);
      void loadReport(report).finally(() => context.consumeNavigationTarget(target.requestId));
    } else {
      setNavigationError(context.language === "zh" ? "目标报告不存在或已被删除。" : "The requested report does not exist or was deleted.");
      context.consumeNavigationTarget(target.requestId);
    }
  }, [active, allReports, context, context.activeVaultId, context.consumeNavigationTarget, context.navigationTarget, context.reportsReady, loadReport]);

  useEffect(() => {
    if (!active) return;
    const target = context.navigationTarget;
    if (target?.kind === "report" && target.vaultId === context.activeVaultId) return;
    const first = filteredReports[0];
    if (!first) {
      if (selected) {
        setSelected(null);
        setSelectedRunEvents([]);
      }
      return;
    }
    if (!selected || reportBucket(selected.summary.kind) !== activeKind) {
      void loadReport(first);
    }
  }, [active, activeKind, context.activeVaultId, context.navigationTarget, filteredReports, loadReport, selected]);

  return (
    <section className="view active reports-page">
      {navigationError && <p className="settings-action-note warning" role="alert">{navigationError}</p>}
      <div className="reports-workspace">
        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>{context.t("latestReports")}</h2>
              <p className="panel-copy">{context.t("reportListCopy")}</p>
            </div>
            <span className="pill">{filteredReports.length} {context.t("reports")}</span>
          </div>
          <div className="report-type-grid" aria-label={context.t("reportWorkflowOverview")}>
            {reportOverview.map((item) => (
              <button className={`report-type-card ${activeKind === item.kind ? "active" : ""}`} key={item.kind} onClick={() => switchReportKind(item.kind)} type="button">
                <span>{context.t(`reportTab.${item.kind}`)}</span>
                <strong>{item.count}</strong>
                <small>{context.t("latestRun")}: {item.latest}</small>
              </button>
            ))}
          </div>
          <div className="page-list">
            {filteredReports.length ? (
              filteredReports.map((report) => (
                <button className={`report-row ${selectedKey(selected) === reportKey(report) ? "active" : ""}`} key={reportKey(report)} onClick={() => {
                  if (context.navigationTarget?.kind === "report") context.consumeNavigationTarget(context.navigationTarget.requestId);
                  setNavigationError(null);
                  void loadReport(report);
                }}>
                  <span className="pill">{localizeReportKind(report.kind, context.t)}</span>
                  <strong>{localizeReportTitle(report.title || report.path, report.kind, context.t)}</strong>
                  <span>
                    {report.updated || context.t("unknown")} · {Math.round(report.size / 1024)} KB
                  </span>
                  <small>{report.path}</small>
                </button>
              ))
            ) : (
              <article className="result-item">
                <p>{context.t("noReportsForType")}</p>
              </article>
            )}
          </div>
        </article>

        <aside className="panel page-preview">
          <div className="panel-header">
            <h2>{context.t("reportDetail")}</h2>
            {selected && <span className="pill">{localizeReportKind(selected.summary.kind, context.t)}</span>}
          </div>
          {loadingReportPath ? (
            <LoadingBlock title={context.t("reportLoading")} copy={context.t("reportLoadingCopy")} />
          ) : selected ? (
            <>
              <ReportSummaryCard
                title={localizeReportTitle(selected.summary.title || selected.path, selected.summary.kind, context.t)}
                subtitle={selected.summary.path}
              />
              <ReportReadableView
                content={selected.content}
                language={context.language}
                t={context.t}
                onOpenPage={(path) => context.openWikiPageInVault(vaultForReport(context, selected.summary).id, path)}
                loadPage={(path) => getPage(selectorForReport(context, selected.summary, vaultForReport(context, selected.summary)), path)}
                inlinePagePreview
              />
              <ReportRunEvents events={selectedRunEvents} t={context.t} language={context.language} />
              <details>
                <summary>{context.t("markdownDetail")}</summary>
                <pre className="markdown-preview">{selected.content}</pre>
              </details>
            </>
          ) : (
            <p className="panel-copy">{context.t("selectReport")}</p>
          )}
        </aside>
      </div>
    </section>
  );
}

function vaultForReport(context: ReportsAppContext, report: ReportSummary) {
  return (
    (report.vault_id ? context.vaultOptions.find((vault) => vault.id === report.vault_id) : null) ||
    (report.vault_path ? context.vaultOptions.find((vault) => vault.path === report.vault_path) : null) ||
    context.vaultOptions.find((vault) => vault.id === context.activeVaultId) || {
      id: context.activeVaultId,
      name: report.vault_name || context.activeVaultId,
      path: context.vaultPath,
    }
  );
}

function selectorForReport(context: ReportsAppContext, report: ReportSummary, vault = vaultForReport(context, report)): VaultSelector {
  return {
    config_path: context.configPath,
    vault_id: report.vault_id || vault.id,
    vault_path: report.vault_path || vault.path,
  };
}

function reportKey(report: ReportSummary | ReportDetail) {
  const summary = "summary" in report ? report.summary : report;
  return `${summary.vault_id || summary.vault_path || "vault"}:${summary.path}`;
}

function selectedKey(report: ReportDetail | null) {
  return report ? reportKey(report) : "";
}

function ReportRunEvents({ events, t, language }: { events: RunEvent[]; t: (key: string) => string; language: ReportsAppContext["language"] }) {
  if (!events.length) return null;
  return (
    <section className="report-run-events">
      <h3>{t("runTimeline")}</h3>
      <div className="run-event-list">
        {events.map((event) => (
          <article className="run-event-item" key={`${event.run_id}:${event.sequence}`}>
            <div>
              <strong>{event.status === "failed" ? userFacingError(event.message, language) : (event.message || event.event_type)}</strong>
              <span>{event.stage} · {runStatusLabel(event.status, t)}</span>
              <FailurePayloadSummary event={event} t={t} />
            </div>
            <time>{event.created_at}</time>
          </article>
        ))}
      </div>
    </section>
  );
}

function FailurePayloadSummary({ event, t }: { event: RunEvent; t: (key: string) => string }) {
  const items = failurePayloadItems(event, t);
  if (!items.length) return null;
  return (
    <ul className="run-event-payload">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function failurePayloadItems(event: RunEvent, t: (key: string) => string) {
  if (event.status !== "partially_failed" && event.event_type !== "run_partially_failed") return [];
  const payload = event.payload || {};
  const stats = asRecord(payload.stats);
  const resultSummary = asRecord(payload.result_summary);
  const source = Object.keys(stats).length ? stats : resultSummary;
  const items: string[] = [];
  for (const key of ["failed_count", "failed_segment_count", "document_processing_failed_count"]) {
    const value = source[key];
    if (typeof value === "number" && value > 0) {
      items.push(`${localizeReportLabel(key, t)}: ${value}`);
    }
  }
  const warnings = payload.warnings;
  if (Array.isArray(warnings) && warnings.length) {
    items.push(`${localizeReportLabel("warnings", t)}: ${warnings.length}`);
  }
  const failedVerifications = Array.isArray(payload.verifications)
    ? payload.verifications.filter((item) => asRecord(item).status === "failed").length
    : 0;
  if (failedVerifications) {
    items.push(`${localizeReportLabel("failed_verifications", t)}: ${failedVerifications}`);
  }
  return items;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function reportBucket(kind: string): "ingest" | "lint" | "query" {
  const normalized = kind.toLowerCase();
  if (normalized.includes("ingest")) return "ingest";
  if (normalized.includes("query")) return "query";
  return "lint";
}
