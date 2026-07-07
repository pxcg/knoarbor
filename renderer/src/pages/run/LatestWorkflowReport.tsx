import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { getPage, getReport, type ReportDetail } from "../../api/client";
import type { AppContext } from "../../appContext";
import { localizeReportKind, localizeReportTitle } from "../../components/reportLabels";
import { InlineHelp } from "../../components/InlineHelp";
import { ReportSummaryCard } from "../../components/report/ReportSummaryCard";

const ReportReadableView = lazy(() => import("../../components/report/ReportReadableView").then((module) => ({ default: module.ReportReadableView })));

type Props = {
  context: AppContext;
  mode: "both" | "ingest" | "lint";
};

export function LatestWorkflowReport({ context, mode }: Props) {
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const latest = useMemo(() => {
    const target = mode === "both" ? null : mode;
    return context.reports.find((report) => {
      const kind = report.kind.toLowerCase();
      if (!target) return kind.includes("ingest") || kind.includes("lint");
      return target === "ingest" ? kind.includes("ingest") : kind.includes("lint") || kind.includes("maintenance");
    });
  }, [context.reports, mode]);

  useEffect(() => {
    let cancelled = false;
    if (!latest) {
      setDetail(null);
      return;
    }
    getReport(context.activeVaultSelector, latest.path)
      .then((report) => {
        if (!cancelled) setDetail(report);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [context.activeVaultSelector, latest]);

  if (!detail) return null;
  const helpKey = mode === "ingest" ? "latestIngestArtifactCopy" : mode === "lint" ? "latestLintArtifactCopy" : "latestRunArtifactCopy";
  return (
    <article className="panel latest-workflow-report">
      <div className="panel-header">
        <div>
          <h2>
            {context.t("latestRunArtifact")}
            <InlineHelp text={context.t(helpKey)} />
          </h2>
        </div>
        <button className="button secondary" type="button" onClick={() => context.openReport(detail.path)}>
          {context.t("openReport")}
        </button>
      </div>
      <ReportSummaryCard
        title={localizeReportTitle(detail.summary.title || detail.path, detail.summary.kind, context.t)}
        subtitle={`${localizeReportKind(detail.summary.kind, context.t)} · ${detail.summary.path}`}
      />
      <Suspense fallback={<p className="panel-copy">{context.t("loading")}</p>}>
        <ReportReadableView
          content={detail.content}
          t={context.t}
          onOpenPage={context.openWikiPage}
          loadPage={(path) => getPage(context.activeVaultSelector, path)}
          inlinePagePreview
        />
      </Suspense>
    </article>
  );
}
