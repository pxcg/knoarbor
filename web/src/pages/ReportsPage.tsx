import { useCallback, useEffect, useMemo, useState } from "react";

import { getPage, getReport, getRunEvents, type ReportDetail } from "../api/client";
import type { AppContext } from "../App";
import { ReportReadableView } from "../components/report/ReportReadableView";
import { parseReportRunId } from "../components/report/reportParser";
import { localizeReportKind, localizeReportLabel, localizeReportTitle } from "../components/reportLabels";
import { runStatusLabel } from "../components/runStatus";
import type { RunEvent } from "../types";

type Props = {
  context: AppContext;
  focusedReportPath?: string | null;
};

export function ReportsPage({ context, focusedReportPath = null }: Props) {
  const [selected, setSelected] = useState<ReportDetail | null>(null);
  const [selectedRunEvents, setSelectedRunEvents] = useState<RunEvent[]>([]);
  const [activeKind, setActiveKind] = useState<"ingest" | "lint" | "query">("lint");
  const filteredReports = useMemo(() => context.reports.filter((report) => reportBucket(report.kind) === activeKind), [activeKind, context.reports]);
  const reportOverview = useMemo(
    () =>
      (["ingest", "lint", "query"] as const).map((kind) => {
        const reports = context.reports.filter((report) => reportBucket(report.kind) === kind);
        return {
          kind,
          count: reports.length,
          latest: reports[0]?.updated || context.t("unknown"),
        };
      }),
    [context.reports, context.t],
  );

  function switchReportKind(kind: "ingest" | "lint" | "query") {
    setActiveKind(kind);
    if (selected && reportBucket(selected.summary.kind) !== kind) {
      setSelected(null);
    }
  }

  const loadReport = useCallback(async (path: string) => {
    try {
      const report = await getReport(context.vaultPath, path);
      setSelected(report);
      setSelectedRunEvents([]);
      const runId = parseReportRunId(report.content);
      if (!runId) {
        return;
      }
      try {
        const events = await getRunEvents(context.vaultPath, runId);
        setSelectedRunEvents(events.events || []);
      } catch {
        setSelectedRunEvents([]);
      }
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }, [context.vaultPath, context.setNotice]);

  useEffect(() => {
    if (!focusedReportPath) return;
    const report = context.reports.find((item) => item.path === focusedReportPath);
    if (report) {
      setActiveKind(reportBucket(report.kind));
    }
    void loadReport(focusedReportPath);
  }, [context.reports, focusedReportPath, loadReport]);

  useEffect(() => {
    const first = filteredReports[0];
    if (!first) {
      if (selected) {
        setSelected(null);
        setSelectedRunEvents([]);
      }
      return;
    }
    if (!selected || reportBucket(selected.summary.kind) !== activeKind) {
      void loadReport(first.path);
    }
  }, [activeKind, filteredReports, loadReport, selected]);

  return (
    <section className="view active">
      <div className="page-intro">
        <div>
          <p className="eyebrow">{context.t("runtimeEvidence")}</p>
          <h2>{context.t("reportsTitle")}</h2>
          <p className="panel-copy">{context.t("reportsSubtitle")}</p>
        </div>
      </div>
      <div className="panel-grid pages-workspace">
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
          <div className="segmented-control report-tabs" aria-label={context.t("reportType")}>
            {(["ingest", "lint", "query"] as const).map((kind) => (
              <button className={activeKind === kind ? "active" : ""} key={kind} onClick={() => switchReportKind(kind)} type="button">
                {context.t(`reportTab.${kind}`)}
              </button>
            ))}
          </div>
          <div className="page-list">
            {filteredReports.length ? (
              filteredReports.map((report) => (
                <button className={`report-row ${selected?.path === report.path ? "active" : ""}`} key={report.path} onClick={() => void loadReport(report.path)}>
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
          {selected ? (
            <>
              <div className="report-summary-card">
                <strong>{localizeReportTitle(selected.summary.title || selected.path, selected.summary.kind, context.t)}</strong>
                <span>{selected.summary.path}</span>
                <p>{context.t("reportReadableHint")}</p>
              </div>
              <ReportReadableView
                content={selected.content}
                t={context.t}
                onOpenPage={context.openWikiPage}
                loadPage={(path) => getPage(context.vaultPath, path)}
                inlinePagePreview
              />
              <ReportRunEvents events={selectedRunEvents} t={context.t} />
              <details open>
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

function ReportRunEvents({ events, t }: { events: RunEvent[]; t: (key: string) => string }) {
  if (!events.length) return null;
  return (
    <section className="report-run-events">
      <h3>{t("runTimeline")}</h3>
      <div className="run-event-list">
        {events.slice(-12).map((event) => (
          <article className="run-event-item" key={`${event.run_id}:${event.sequence}`}>
            <div>
              <strong>{event.message || event.event_type}</strong>
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
