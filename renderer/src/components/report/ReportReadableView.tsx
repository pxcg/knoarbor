import { useState } from "react";

import type { PageDetail } from "../../api/client";
import { localizeReportLabel, localizeReportSection, localizeReportValue } from "../reportLabels";
import { ReportArtifactsSection } from "./ReportArtifactsSection";
import { ReportExecutiveSummary } from "./ReportExecutiveSummary";
import { ReportValue } from "./ReportValue";
import { isWikiPagePath, parseReport, parseReportArtifacts } from "./reportParser";
import type { Language } from "../../types";
import { userFacingError } from "../../userFacingError";

type ReportReadableViewProps = {
  content: string;
  t: (key: string) => string;
  onOpenPage: (path: string) => void;
  loadPage?: (path: string) => Promise<PageDetail>;
  inlinePagePreview?: boolean;
  language: Language;
};

export function ReportReadableView({ content, t, onOpenPage, loadPage, inlinePagePreview = false, language }: ReportReadableViewProps) {
  const report = parseReport(content);
  const artifacts = parseReportArtifacts(content);
  const wikiWrittenPages = artifacts.writtenPages.filter((artifact) => isWikiPagePath(artifact.path)).length;
  const [preview, setPreview] = useState<PageDetail | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  async function previewPage(path: string) {
    if (!loadPage) return;
    if (previewPath === path && preview) {
      setPreviewPath(null);
      setPreview(null);
      setPreviewError(null);
      return;
    }
    setPreviewPath(path);
    setPreview(null);
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      setPreview(await loadPage(path));
    } catch (error) {
      setPreviewError(userFacingError(error, language));
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <div>
      <ReportExecutiveSummary
        changedPages={artifacts.changedPages.length}
        failures={artifacts.failures.length}
        metrics={report.metrics}
        t={t}
        writtenPages={wikiWrittenPages}
      />
      <ReportArtifactsSection
        artifacts={artifacts}
        inlinePagePreview={inlinePagePreview}
        loadPage={loadPage}
        preview={preview}
        previewError={previewError}
        previewLoading={previewLoading}
        previewPath={previewPath}
        t={t}
        onOpenPage={onOpenPage}
        onPreviewPage={previewPage}
        language={language}
      />
      {(!!report.metrics.length || !!report.sections.length) && (
        <details className="report-technical-details">
          <summary>{t("reportTechnicalDetails")}</summary>
          <div className="report-technical-content">
            {!!report.metrics.length && (
              <section>
                <h3>{t("keyMetrics")}</h3>
                <dl className="report-metrics">
                  {report.metrics.map((metric) => (
                    <div className="report-metric" key={metric.key}>
                      <dt>{localizeReportLabel(metric.key, t)}</dt>
                      <dd>{localizeReportValue(metric.value, t)}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
            {!!report.sections.length && (
              <section>
                <h3>{t("reportSections")}</h3>
                <div className="report-section-list">
                  {report.sections.map((section) => (
                    <article className="report-section-card" key={section.title}>
                      <h3>{localizeReportSection(section.title, t)}</h3>
                      {section.items.length ? (
                        <ul>
                          {section.items.map((item) => (
                            <li key={`${item.key || ""}:${item.value}`}>
                              {item.key ? (
                                <>
                                  <strong>{localizeReportLabel(item.key, t)}：</strong>
                                  <ReportValue value={item.value} t={t} onOpenPage={onOpenPage} />
                                </>
                              ) : (
                                <ReportValue value={item.value} t={t} onOpenPage={onOpenPage} />
                              )}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="panel-copy">{t("noSummary")}</p>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            )}
          </div>
        </details>
      )}
    </div>
  );
}
