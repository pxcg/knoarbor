import { useState } from "react";

import type { PageDetail } from "../../api/client";
import { AsyncMarkdownPreview } from "../AsyncMarkdownPreview";
import { PagePathLinks } from "../PagePathLinks";
import { localizeReportLabel, localizeReportSection, localizeReportValue } from "../reportLabels";
import {
  extractWikiPagePaths,
  getReportMetricNumber,
  type PageArtifact,
  pageName,
  parseReport,
  parseReportArtifacts,
} from "./reportParser";

type ReportReadableViewProps = {
  content: string;
  t: (key: string) => string;
  onOpenPage: (path: string) => void;
  loadPage?: (path: string) => Promise<PageDetail>;
  inlinePagePreview?: boolean;
};

export function ReportReadableView({ content, t, onOpenPage, loadPage, inlinePagePreview = false }: ReportReadableViewProps) {
  const report = parseReport(content);
  const artifacts = parseReportArtifacts(content);
  const pageArtifacts = [...artifacts.changedPages, ...artifacts.writtenPages, ...artifacts.relatedPages];
  const legacyChangeCount = getReportMetricNumber(content, "applied_operations");
  const hasLegacyChangesWithoutDiff = legacyChangeCount > 0 && artifacts.changedPages.length === 0 && !content.includes("## Page Changes");
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
      setPreviewError(error instanceof Error ? error.message : String(error));
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
        writtenPages={artifacts.writtenPages.length}
      />
      {!!pageArtifacts.length && (
        <section className="report-artifact-section">
          <h3>{t("reportArtifacts")}</h3>
          <ReportArtifactGroup
            title={t("reportChangedPages")}
            artifacts={artifacts.changedPages}
            previewPath={previewPath}
            preview={preview}
            previewLoading={previewLoading}
            previewError={previewError}
            inlinePagePreview={inlinePagePreview}
            loadPage={loadPage}
            t={t}
            onOpenPage={onOpenPage}
            onPreviewPage={previewPage}
          />
          <ReportArtifactGroup
            title={t("reportWrittenPages")}
            artifacts={artifacts.writtenPages}
            previewPath={previewPath}
            preview={preview}
            previewLoading={previewLoading}
            previewError={previewError}
            inlinePagePreview={inlinePagePreview}
            loadPage={loadPage}
            t={t}
            onOpenPage={onOpenPage}
            onPreviewPage={previewPage}
          />
          <ReportArtifactGroup
            title={t("reportRelatedPages")}
            artifacts={artifacts.relatedPages}
            previewPath={previewPath}
            preview={preview}
            previewLoading={previewLoading}
            previewError={previewError}
            inlinePagePreview={inlinePagePreview}
            loadPage={loadPage}
            t={t}
            onOpenPage={onOpenPage}
            onPreviewPage={previewPage}
          />
        </section>
      )}
      {!!artifacts.failures.length && (
        <section className="report-artifact-section">
          <h3>{t("reportFailures")}</h3>
          <div className="report-failure-list">
            {artifacts.failures.map((failure, index) => (
              <article className="report-failure-card" key={`${failure.source || "failure"}:${index}`}>
                {failure.source && <strong>{failure.source}</strong>}
                <p>{failure.message}</p>
                <div>
                  {failure.stage && <span className="pill">{failure.stage}</span>}
                  {failure.code && <span className="pill danger">{failure.code}</span>}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
      {hasLegacyChangesWithoutDiff && (
        <section className="report-artifact-section">
          <div className="report-diff-unavailable">
            <strong>{t("reportDiffUnavailableTitle")}</strong>
            <p>{t("reportDiffUnavailableCopy")}</p>
          </div>
        </section>
      )}
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

function ReportExecutiveSummary({
  changedPages,
  failures,
  metrics,
  t,
  writtenPages,
}: {
  changedPages: number;
  failures: number;
  metrics: Array<{ key: string; value: string }>;
  t: (key: string) => string;
  writtenPages: number;
}) {
  const metricMap = new Map(metrics.map((metric) => [normalizeMetricKey(metric.key), metric.value]));
  const appliedOperations = pickMetric(metricMap, ["appliedoperations", "applied_operations"]);
  const totalTokens = pickMetric(metricMap, ["totaltokens", "total_tokens"]);
  const elapsed = pickMetric(metricMap, ["elapsedseconds", "elapsed_seconds", "durationseconds", "duration_seconds"]);
  const status = failures > 0 ? t("reportNeedsAttention") : changedPages || writtenPages || appliedOperations ? t("reportCompletedWithChanges") : t("reportNoActionNeeded");
  const cards = [
    { label: t("reportOutcome"), value: status },
    { label: t("reportWrittenPages"), value: String(writtenPages) },
    { label: t("reportChangedPages"), value: String(changedPages) },
    { label: t("reportFailures"), value: String(failures), danger: failures > 0 },
    totalTokens ? { label: t("totalTokens"), value: localizeReportValue(totalTokens, t) } : null,
    elapsed ? { label: t("elapsed"), value: `${localizeReportValue(elapsed, t)}s` } : null,
  ].filter((item): item is { label: string; value: string; danger?: boolean } => Boolean(item));
  return (
    <section className="report-executive-summary">
      <div>
        <h3>{t("reportExecutiveSummary")}</h3>
        <p>{t("reportExecutiveSummaryCopy")}</p>
      </div>
      <dl>
        {cards.map((card) => (
          <div className={card.danger ? "danger" : ""} key={card.label}>
            <dt>{card.label}</dt>
            <dd>{card.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function normalizeMetricKey(key: string) {
  return key.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function pickMetric(metrics: Map<string, string>, keys: string[]) {
  for (const key of keys) {
    const value = metrics.get(normalizeMetricKey(key));
    if (value && value !== "n/a" && value !== "N/A") return value;
  }
  return null;
}

function ReportArtifactGroup({
  title,
  artifacts,
  previewPath,
  preview,
  previewLoading,
  previewError,
  inlinePagePreview,
  loadPage,
  t,
  onOpenPage,
  onPreviewPage,
}: {
  title: string;
  artifacts: PageArtifact[];
  previewPath: string | null;
  preview: PageDetail | null;
  previewLoading: boolean;
  previewError: string | null;
  inlinePagePreview: boolean;
  loadPage?: (path: string) => Promise<PageDetail>;
  t: (key: string) => string;
  onOpenPage: (path: string) => void;
  onPreviewPage: (path: string) => Promise<void>;
}) {
  if (!artifacts.length) return null;
  return (
    <div className="report-artifact-group">
      <h4>{title}</h4>
      <div className="report-artifact-grid">
        {artifacts.map((artifact) => (
          <article className={`report-page-card ${previewPath === artifact.path ? "active" : ""}`} key={`${artifact.kind}:${artifact.path}`}>
            <div className="report-page-card-header">
              <button
                className="report-page-main"
                type="button"
                onClick={() => (inlinePagePreview && loadPage ? void onPreviewPage(artifact.path) : onOpenPage(artifact.path))}
              >
                <strong>{pageName(artifact.path)}</strong>
                <span>{artifact.path}</span>
              </button>
              <div className="report-page-actions">
                {!!artifact.changes.length && <span className="pill">{t("reportPageChanges")}</span>}
                {inlinePagePreview && loadPage && (
                  <button className="button secondary small-button" type="button" onClick={() => void onPreviewPage(artifact.path)}>
                    {previewPath === artifact.path && preview ? t("collapseContent") : t("expandContent")}
                  </button>
                )}
                <button className="button secondary small-button" type="button" onClick={() => onOpenPage(artifact.path)}>
                  {t("viewInKnowledgeBase")}
                </button>
              </div>
            </div>
            {!!artifact.changes.length && (
              <div className="report-page-change-list">
                {artifact.changes.map((change, index) => (
                  <div className="report-page-change" key={`${change.page}:${index}`}>
                    <div className="report-page-change-meta">
                      {change.action && <span className="pill">{localizeOperationAction(change.action, t)}</span>}
                      {change.summary && <span>{change.summary}</span>}
                    </div>
                    {!!change.diff.length && <DiffBlock lines={change.diff} />}
                  </div>
                ))}
              </div>
            )}
            {inlinePagePreview && previewPath === artifact.path && (
              <ReportInlinePreview
                loading={previewLoading}
                preview={preview}
                previewError={previewError}
                previewPath={previewPath}
                t={t}
                onOpenPage={onOpenPage}
              />
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

function ReportInlinePreview({
  loading,
  preview,
  previewError,
  previewPath,
  t,
  onOpenPage,
}: {
  loading: boolean;
  preview: PageDetail | null;
  previewError: string | null;
  previewPath: string | null;
  t: (key: string) => string;
  onOpenPage: (path: string) => void;
}) {
  return (
    <article className="report-inline-preview">
      <div className="report-inline-preview-header">
        <div>
          <h3>{preview?.summary.title || previewPath || t("wikiPagePreview")}</h3>
          {preview && <span>{preview.path}</span>}
        </div>
      </div>
      {loading && <p className="panel-copy">{t("loading")}</p>}
      {previewError && <p className="panel-copy warning">{previewError}</p>}
      {preview && (
        <AsyncMarkdownPreview
          className="wiki-markdown-preview report-markdown-preview"
          content={preview.content}
          stripFrontmatter
          onOpenWikiPage={onOpenPage}
        />
      )}
    </article>
  );
}

function ReportValue({ value, t, onOpenPage }: { value: string; t: (key: string) => string; onOpenPage: (path: string) => void }) {
  const structured = structuredReportValue(value, t, onOpenPage);
  if (structured) return structured;
  const localized = localizeReportValue(value, t);
  const paths = extractWikiPagePaths(value);
  if (!paths.length) return <>{localized}</>;
  return (
    <>
      {localized}
      <PagePathLinks links={paths.map((path) => ({ path }))} inline onOpenPage={onOpenPage} />
    </>
  );
}

function structuredReportValue(value: string, t: (key: string) => string, onOpenPage: (path: string) => void) {
  const issue = value.match(/^\[(\w+)]\s+`([^`]+)`\s+in\s+`([^`]+)`:\s+(.+)$/);
  if (issue) {
    return (
      <span className="report-structured-line">
        <span className="pill">{localizeSeverity(issue[1], t)}</span>
        <code>{localizeIssueCode(issue[2], t)}</code>
        <button type="button" onClick={() => onOpenPage(issue[3])}>
          {issue[3]}
        </button>
        <span>{localizeReportSentence(issue[4], t)}</span>
      </span>
    );
  }

  const candidate = value.match(/^`([^`]+)`\s+(\S+)\s+(\S+)\s+->\s+(.+)$/);
  if (candidate) {
    return (
      <span className="report-structured-line">
        <span className="pill">{t("reportCandidate")}</span>
        <code>{localizeCandidateKind(candidate[2], t)}</code>
        <code>{localizeOperationAction(candidate[3], t)}</code>
        <button type="button" onClick={() => onOpenPage(candidate[4])}>
          {candidate[4]}
        </button>
        <small>{candidate[1]}</small>
      </span>
    );
  }

  const decision = value.match(/^\[(approve|reject)]\s+operation\s+(\d+)\s+(\S+)\s+risk=(\w+):\s+(.+)$/);
  if (decision) {
    return (
      <span className="report-structured-line decision-line">
        <span className={`pill ${decision[1] === "reject" ? "danger" : "success"}`}>{localizeDecision(decision[1], t)}</span>
        <code>{`${t("operation")} ${decision[2]}`}</code>
        <code>{localizeExecutorFit(decision[3], t)}</code>
        <code>{`${t("risk")}: ${localizeRisk(decision[4], t)}`}</code>
        <span>{localizeReportSentence(decision[5], t)}</span>
      </span>
    );
  }

  const queued = value.match(/^\[(\w+)]\s+`([^`]+)`\s+on\s+`([^`]+)`\s+risk=(\w+):\s+(.+)$/);
  if (queued) {
    return (
      <span className="report-structured-line">
        <span className="pill">{localizeOperationAction(queued[1], t)}</span>
        <code>{localizeOperationAction(queued[2], t)}</code>
        <button type="button" onClick={() => onOpenPage(queued[3])}>
          {queued[3]}
        </button>
        <code>{`${t("risk")}: ${localizeRisk(queued[4], t)}`}</code>
        <span>{localizeReportSentence(queued[5], t)}</span>
      </span>
    );
  }

  return null;
}

function DiffBlock({ lines }: { lines: string[] }) {
  return (
    <pre className="report-diff">
      {lines.map((line, index) => (
        <span className={diffLineClass(line)} key={`${index}:${line}`}>
          {line}
        </span>
      ))}
    </pre>
  );
}

function diffLineClass(line: string) {
  if (line.startsWith("+") && !line.startsWith("+++")) return "diff-add";
  if (line.startsWith("-") && !line.startsWith("---")) return "diff-remove";
  if (line.startsWith("@@")) return "diff-hunk";
  return "diff-context";
}

function localizeSeverity(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized;
  return { error: "错误", warning: "警告", info: "提示" }[normalized] || value;
}

function localizeDecision(value: string, t: (key: string) => string) {
  if (!isChinese(t)) return value === "approve" ? "Approved" : "Rejected";
  return value === "approve" ? "通过" : "拒绝";
}

function localizeRisk(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized;
  return { safe: "安全", low: "低", medium: "中", high: "高" }[normalized] || value;
}

function localizeCandidateKind(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized.replace(/_/g, " ");
  return {
    deterministic_wiki_operation: "确定性维护操作",
    report_only: "仅报告",
    page_draft: "页面草稿",
  }[normalized] || normalized.replace(/_/g, " ");
}

function localizeExecutorFit(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized.replace(/_/g, " ");
  return {
    supported_by_wiki_operation: "可由维护操作执行",
    supported_by_report_only: "适合仅报告",
    supported_by_refresh_request: "需要刷新请求",
    unsupported: "暂不支持自动执行",
  }[normalized] || normalized.replace(/_/g, " ");
}

function localizeOperationAction(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized.replace(/_/g, " ");
  return {
    add_missing_section: "补充缺失章节",
    attach_related_pages: "补充关联页面",
    attach_source_digest: "补充来源摘要链接",
    deduplicate_section_items: "去重章节条目",
    deterministic_wiki_operation: "确定性维护操作",
    normalize_wikilink: "规范 Wiki 链接",
    remove_adjacent_duplicate_headings: "移除相邻重复标题",
    remove_related_links: "移除关联链接",
    replace_wikilink: "替换 Wiki 链接",
    report_only: "仅报告",
    update_frontmatter: "更新元数据",
    update_source_field: "同步来源字段",
  }[normalized] || normalized.replace(/_/g, " ");
}

function localizeIssueCode(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized;
  return {
    adjacent_duplicate_heading: "相邻重复标题",
    broken_wikilink: "失效 Wiki 链接",
    duplicate_title: "重复标题",
    source_section_mismatch: "来源字段不一致",
  }[normalized] || normalized;
}

function localizeReportSentence(value: string, t: (key: string) => string) {
  if (!isChinese(t)) return value;
  const normalized = value.trim();
  const known: Record<string, string> = {
    "Frontmatter source and Source section are not synchronized.": "页面元数据中的 source 与正文 Source 章节不一致。",
    "No deterministic issues.": "没有确定性问题。",
    "No semantic candidates.": "没有语义候选项。",
    "No review decisions.": "没有评审决策。",
    "No queued report-only or refresh-request actions.": "没有排队的仅报告或刷新请求。",
    "No reviewed changes applied.": "没有应用评审通过的修改。",
    "The proposed update_source_field only syncs the frontmatter to the first source, but the Source section contains an extra source that is not addressed. The operation is incomplete; manual review or alternative action (remove extra source or use a list) is required.":
      "提议的来源字段同步只会把元数据同步到第一个来源，但 Source 章节还有额外来源没有处理。该操作不完整，需要人工检查，或改用移除额外来源/支持来源列表的维护方式。",
  };
  return known[normalized] || normalized;
}

function isChinese(t: (key: string) => string): boolean {
  return t("language") === "语言";
}
