import { useState } from "react";

import type { PageDetail } from "../../api/client";
import { MarkdownPreview } from "../MarkdownPreview";
import { localizeReportLabel, localizeReportSection, localizeReportValue } from "../reportLabels";
import {
  buildPageArtifacts,
  extractWikiPagePaths,
  getReportMetricNumber,
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
  const pageArtifacts = buildPageArtifacts(artifacts.pages, artifacts.changes);
  const legacyChangeCount = getReportMetricNumber(content, "applied_operations");
  const hasLegacyChangesWithoutDiff = legacyChangeCount > 0 && artifacts.changes.length === 0 && !content.includes("## Page Changes");
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
      {!!pageArtifacts.length && (
        <section className="report-artifact-section">
          <h3>{t("reportArtifacts")}</h3>
          <div className="report-artifact-grid">
            {pageArtifacts.map((artifact) => (
              <article className={`report-page-card ${previewPath === artifact.path ? "active" : ""}`} key={artifact.path}>
                <div className="report-page-card-header">
                  <button
                    className="report-page-main"
                    type="button"
                    onClick={() => (inlinePagePreview && loadPage ? void previewPage(artifact.path) : onOpenPage(artifact.path))}
                  >
                    <strong>{pageName(artifact.path)}</strong>
                    <span>{artifact.path}</span>
                  </button>
                  <div className="report-page-actions">
                    {!!artifact.changes.length && <span className="pill">{t("reportPageChanges")}</span>}
                    {inlinePagePreview && loadPage && (
                      <button className="button secondary small-button" type="button" onClick={() => void previewPage(artifact.path)}>
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
      <h3>{t("reportOverview")}</h3>
      {!!report.metrics.length && (
        <>
          <h3>{t("keyMetrics")}</h3>
          <dl className="report-metrics">
            {report.metrics.map((metric) => (
              <div className="report-metric" key={metric.key}>
                <dt>{localizeReportLabel(metric.key, t)}</dt>
                <dd>{localizeReportValue(metric.value, t)}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      {!!report.sections.length && (
        <>
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
        </>
      )}
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
        <MarkdownPreview
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
      <PagePathLinks paths={paths} onOpenPage={onOpenPage} />
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

function PagePathLinks({ paths, onOpenPage }: { paths: string[]; onOpenPage: (path: string) => void }) {
  return (
    <span className="page-path-links inline-links">
      {paths.map((path) => (
        <button key={path} type="button" onClick={() => onOpenPage(path)}>
          {path}
        </button>
      ))}
    </span>
  );
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
