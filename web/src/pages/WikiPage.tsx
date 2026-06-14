import { useEffect, useMemo, useState } from "react";

import { getPage, type PageDetail, type PageLink, type PageSummary } from "../api/client";
import type { AppContext } from "../App";
import { AsyncMarkdownPreview } from "../components/AsyncMarkdownPreview";
import { DelayedTooltip } from "../components/DelayedTooltip";
import { PagePathLinks } from "../components/PagePathLinks";

type Props = {
  context: AppContext;
  focusedPagePath?: string | null;
};

const PAGE_DIRECTORIES = ["sources", "entities", "concepts", "comparisons", "queries", "workflows"];

export function WikiPage({ context, focusedPagePath = null }: Props) {
  const [selectedPath, setSelectedPath] = useState<string | null>(focusedPagePath);
  const [selectedDetail, setSelectedDetail] = useState<PageDetail | null>(null);
  const [directory, setDirectory] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const directoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const page of context.pages) {
      counts.set(page.directory, (counts.get(page.directory) || 0) + 1);
    }
    return counts;
  }, [context.pages]);

  const filteredPages = useMemo(() => {
    const query = search.trim().toLowerCase();
    return context.pages.filter((page) => {
      if (directory && page.directory !== directory) return false;
      if (!query) return true;
      return `${page.title} ${page.path} ${page.summary} ${page.tags.join(" ")}`.toLowerCase().includes(query);
    });
  }, [context.pages, directory, search]);

  useEffect(() => {
    if (focusedPagePath) setSelectedPath(focusedPagePath);
  }, [focusedPagePath]);

  useEffect(() => {
    setSelectedDetail(null);
    if (!focusedPagePath) setSelectedPath(null);
  }, [context.activeVaultId, focusedPagePath]);

  useEffect(() => {
    if (selectedPath && filteredPages.some((page) => page.path === selectedPath)) return;
    const nextPath = filteredPages[0]?.path || null;
    if (nextPath !== selectedPath) {
      setSelectedPath(nextPath);
    }
    if (!nextPath) setSelectedDetail(null);
  }, [filteredPages, selectedPath]);

  useEffect(() => {
    if (!selectedPath) {
      setSelectedDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getPage(context.activeVaultSelector, selectedPath)
      .then((detail) => {
        if (!cancelled) setSelectedDetail(detail);
      })
      .catch((error) => {
        if (!cancelled) context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [context.activeVaultSelector, context.setNotice, selectedPath]);

  return (
    <section className="view active">
      <div className="wiki-workspace">
        <aside className="panel wiki-directory-panel">
          <div className="panel-header compact">
            <h2>{context.t("wikiDirectory")}</h2>
          </div>
          <div className="wiki-directory-section">
            <button className={`wiki-directory-row ${directory === "" ? "active" : ""}`} onClick={() => setDirectory("")} type="button">
              <span>{context.t("allPages")}</span>
              <strong>{context.pages.length}</strong>
            </button>
            {PAGE_DIRECTORIES.filter((item) => directoryCounts.has(item)).map((item) => (
              <button className={`wiki-directory-row ${directory === item ? "active" : ""}`} key={item} onClick={() => setDirectory(item)} type="button">
                <span>{item}</span>
                <strong>{directoryCounts.get(item) || 0}</strong>
              </button>
            ))}
          </div>
        </aside>

        <article className="panel wiki-list-panel">
          <div className="panel-header compact">
            <h2>{context.t("wikiPageList")}</h2>
            <span className="pill">{`${filteredPages.length} ${context.t("pages")}`}</span>
          </div>
          <label className="field compact-field">
            <span>{context.t("search")}</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={context.t("wikiSearchPlaceholder")} />
          </label>
          <div className="page-list wiki-page-list">
            {filteredPages.length ? (
              filteredPages.map((page) => (
                <WikiPageRow key={page.path} page={page} active={selectedPath === page.path} onClick={() => setSelectedPath(page.path)} />
              ))
            ) : (
              <article className="result-item">
                <p>{context.t("noPages")}</p>
              </article>
            )}
          </div>
        </article>

        <aside className="panel wiki-preview-panel">
          <div className="panel-header">
            <div>
              <h2>{selectedDetail?.summary.title || context.t("wikiPagePreview")}</h2>
              <p className="panel-copy">{selectedDetail?.path || context.t("wikiNoSelection")}</p>
            </div>
            {selectedDetail && (
              <div className="button-row compact-row">
                <button className="button secondary" type="button" onClick={() => askAboutPage(context, selectedDetail)}>{context.t("askInChat")}</button>
                <button className="button secondary" type="button" onClick={() => context.openPageInGraph(selectedDetail.path)}>{context.t("openInGraph")}</button>
              </div>
            )}
          </div>
          {loading && <p className="panel-copy">{context.t("loading")}</p>}
          {!loading && selectedDetail ? (
            <>
              <PageMetadata detail={selectedDetail} t={context.t} />
              <LinkSection title={context.t("backlinks")} links={selectedDetail.backlinks} direction="backlinks" onOpen={context.openWikiPage} emptyText={context.t("none")} />
              <LinkSection title={context.t("outboundLinks")} links={selectedDetail.outbound_links} direction="outbound" onOpen={context.openWikiPage} emptyText={context.t("none")} />
              <AsyncMarkdownPreview content={selectedDetail.content} className="wiki-markdown-preview" stripFrontmatter onOpenWikiPage={context.openWikiPage} />
            </>
          ) : (
            !loading && <p className="panel-copy">{context.t("wikiNoSelection")}</p>
          )}
        </aside>
      </div>
    </section>
  );
}

function WikiPageRow({ page, active, onClick }: { page: PageSummary; active: boolean; onClick: () => void }) {
  return (
    <button className={`page-row ${active ? "active" : ""}`} onClick={onClick} type="button">
      <span className="page-row-heading">
        <DelayedTooltip text={page.title} className="page-row-title" />
        <span className="page-row-type">{page.directory}</span>
      </span>
      <code>{page.path}</code>
      {page.summary && <small>{page.summary}</small>}
    </button>
  );
}

function askAboutPage(context: AppContext, detail: PageDetail) {
  const title = detail.summary.title || detail.path;
  context.openChatWithPrompt(`请阅读并解释知识库页面「${title}」（${detail.path}），结合页面内容回答我的后续问题。`, context.activeVaultId);
}

function PageMetadata({ detail, t }: { detail: PageDetail; t: (key: string) => string }) {
  return (
    <dl className="mini-detail wiki-meta">
      <div>
        <dt>{t("pagePath")}</dt>
        <dd>{detail.path}</dd>
      </div>
      <div>
        <dt>{t("source")}</dt>
        <dd>{detail.summary.source || t("none")}</dd>
      </div>
      <div>
        <dt>{t("status")}</dt>
        <dd>{detail.summary.status || t("unknown")}</dd>
      </div>
      <div>
        <dt>{t("pageSummary")}</dt>
        <dd>{detail.summary.summary || t("noSummary")}</dd>
      </div>
    </dl>
  );
}

function LinkSection({
  title,
  links,
  direction,
  onOpen,
  emptyText,
}: {
  title: string;
  links: PageLink[];
  direction: "backlinks" | "outbound";
  onOpen: (path: string) => void;
  emptyText: string;
}) {
  const resolved = links
    .map((link) => ({
      label: direction === "backlinks" ? link.source : (link.target_path || link.target),
      path: direction === "backlinks" ? link.source : link.target_path,
    }))
    .filter((link): link is { label: string; path: string } => Boolean(link.path));
  return (
    <section className="wiki-link-section">
      <h3>{title}</h3>
      {resolved.length ? (
        <PagePathLinks
          links={resolved}
          onOpenPage={onOpen}
        />
      ) : (
        <p className="panel-copy">{emptyText}</p>
      )}
    </section>
  );
}
