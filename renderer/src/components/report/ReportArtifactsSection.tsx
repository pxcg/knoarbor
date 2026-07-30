import type { PageDetail } from "../../api/client";
import { AsyncMarkdownPreview } from "../AsyncMarkdownPreview";
import type { PageArtifact, ReportArtifacts } from "./reportParser";
import { isWikiPagePath, pageName } from "./reportParser";
import { ReportDiffBlock } from "./ReportDiffBlock";
import { localizeOperationAction } from "./reportReadableLocalizers";
import type { Language } from "../../types";
import { userFacingError } from "../../userFacingError";

type ReportArtifactsSectionProps = {
  artifacts: ReportArtifacts;
  inlinePagePreview: boolean;
  loadPage?: (path: string) => Promise<PageDetail>;
  preview: PageDetail | null;
  previewError: string | null;
  previewLoading: boolean;
  previewPath: string | null;
  t: (key: string) => string;
  onOpenPage: (path: string) => void;
  onPreviewPage: (path: string) => Promise<void>;
  language: Language;
};

export function ReportArtifactsSection({
  artifacts,
  inlinePagePreview,
  loadPage,
  preview,
  previewError,
  previewLoading,
  previewPath,
  t,
  onOpenPage,
  onPreviewPage,
  language,
}: ReportArtifactsSectionProps) {
  const pageArtifacts = [...artifacts.changedPages, ...artifacts.writtenPages, ...artifacts.relatedPages];
  return (
    <>
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
            onPreviewPage={onPreviewPage}
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
            onPreviewPage={onPreviewPage}
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
            onPreviewPage={onPreviewPage}
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
                <p>{userFacingError(failure.message, language)}</p>
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
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
        {artifacts.map((artifact) => {
          const canOpenInWiki = isWikiPagePath(artifact.path);
          return (
          <article className={`report-page-card ${previewPath === artifact.path ? "active" : ""}`} key={`${artifact.kind}:${artifact.path}`}>
            <div className="report-page-card-header">
              <button
                className="report-page-main"
                type="button"
                onClick={() => (inlinePagePreview && loadPage ? void onPreviewPage(artifact.path) : canOpenInWiki ? onOpenPage(artifact.path) : undefined)}
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
                {canOpenInWiki && (
                  <button className="button secondary small-button" type="button" onClick={() => onOpenPage(artifact.path)}>
                    {t("viewInKnowledgeBase")}
                  </button>
                )}
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
                    {!!change.diff.length && <ReportDiffBlock lines={change.diff} />}
                  </div>
                ))}
              </div>
            )}
            {inlinePagePreview && previewPath === artifact.path && (
              <ReportInlinePreview loading={previewLoading} preview={preview} previewError={previewError} previewPath={previewPath} t={t} onOpenPage={onOpenPage} />
            )}
          </article>
          );
        })}
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
      {preview && <AsyncMarkdownPreview className="wiki-markdown-preview report-markdown-preview" content={preview.content} stripFrontmatter onOpenWikiPage={onOpenPage} />}
    </article>
  );
}
