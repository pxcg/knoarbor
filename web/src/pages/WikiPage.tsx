import { useEffect, useMemo, useState } from "react";

import { getPage, type PageDetail, type PageLink, type PageSummary } from "../api/client";
import type { AppContext } from "../App";
import { AsyncMarkdownPreview } from "../components/AsyncMarkdownPreview";
import { DelayedTooltip } from "../components/DelayedTooltip";
import { LoadingBlock } from "../components/LoadingBlock";
import { PagePathLinks } from "../components/PagePathLinks";

type Props = {
  context: AppContext;
  focusedPagePath?: string | null;
};

type PageFilter =
  | { type: "all"; value: "" }
  | { type: "role"; value: string }
  | { type: "kind"; value: string }
  | { type: "facet"; value: string };

export function WikiPage({ context, focusedPagePath = null }: Props) {
  const [selectedPath, setSelectedPath] = useState<string | null>(focusedPagePath);
  const [selectedDetail, setSelectedDetail] = useState<PageDetail | null>(null);
  const [filter, setFilter] = useState<PageFilter>({ type: "all", value: "" });
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const pageKindCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const page of context.pages) {
      const pageKind = pageKindOf(page);
      counts.set(pageKind, (counts.get(pageKind) || 0) + 1);
    }
    return counts;
  }, [context.pages]);

  const sourceAuditCount = useMemo(() => context.pages.filter(isSourceDigestPage).length, [context.pages]);

  const facetCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const page of context.pages) {
      for (const facet of facetsOf(page)) {
        if (facet === pageKindOf(page) || facet === page.directory) continue;
        counts.set(facet, (counts.get(facet) || 0) + 1);
      }
    }
    return new Map([...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 12));
  }, [context.pages]);

  const filteredPages = useMemo(() => {
    const query = search.trim().toLowerCase();
    return context.pages.filter((page) => {
      if (!matchesFilter(page, filter)) return false;
      if (!query) return true;
      return `${page.title} ${page.path} ${page.summary} ${page.tags.join(" ")} ${facetsOf(page).join(" ")}`.toLowerCase().includes(query);
    });
  }, [context.pages, filter, search]);

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
            <button className={`wiki-directory-row ${filter.type === "all" ? "active" : ""}`} onClick={() => setFilter({ type: "all", value: "" })} type="button">
              <span>{context.t("allPages")}</span>
              <strong>{context.pages.length}</strong>
            </button>
            {sourceAuditCount > 0 && (
              <button className={`wiki-directory-row ${filter.type === "role" && filter.value === "source_digest" ? "active" : ""}`} onClick={() => setFilter({ type: "role", value: "source_digest" })} type="button">
                <span>{context.t("sourceAudit")}</span>
                <strong>{sourceAuditCount}</strong>
              </button>
            )}
          </div>
          <div className="wiki-directory-section">
            <p className="wiki-directory-label">{context.t("pageKinds")}</p>
            {[...pageKindCounts.entries()].map(([item, count]) => (
              <button className={`wiki-directory-row ${filter.type === "kind" && filter.value === item ? "active" : ""}`} key={item} onClick={() => setFilter({ type: "kind", value: item })} type="button">
                <span>{labelForPageKind(item)}</span>
                <strong>{count}</strong>
              </button>
            ))}
          </div>
          {facetCounts.size > 0 && (
            <div className="wiki-directory-section">
              <p className="wiki-directory-label">{context.t("facets")}</p>
              {[...facetCounts.entries()].map(([item, count]) => (
                <button className={`wiki-directory-row ${filter.type === "facet" && filter.value === item ? "active" : ""}`} key={item} onClick={() => setFilter({ type: "facet", value: item })} type="button">
                  <span>{labelForFacet(item)}</span>
                  <strong>{count}</strong>
                </button>
              ))}
            </div>
          )}
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
          {loading && <LoadingBlock title={context.t("wikiPageLoading")} copy={context.t("wikiPageLoadingCopy")} />}
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
        <span className="page-row-type">{labelForPageKind(pageKindOf(page))}</span>
      </span>
      <code>{page.path}</code>
      {page.summary && <small>{page.summary}</small>}
    </button>
  );
}

function askAboutPage(context: AppContext, detail: PageDetail) {
  const title = detail.summary.title || detail.path;
  context.openChatWithPrompt(`请阅读并解释「${title}」（${detail.path}），并回答我的后续问题。`, context.activeVaultId);
}

function PageMetadata({ detail, t }: { detail: PageDetail; t: (key: string) => string }) {
  return (
    <dl className="mini-detail wiki-meta">
      <div>
        <dt>{t("pagePath")}</dt>
        <dd>{detail.path}</dd>
      </div>
      <div>
        <dt>{t("pageKind")}</dt>
        <dd>{labelForPageKind(pageKindOf(detail.summary))}</dd>
      </div>
      <div>
        <dt>{t("pageRole")}</dt>
        <dd>{detail.summary.role || (isSourceDigestPage(detail.summary) ? "source_digest" : "knowledge_page")}</dd>
      </div>
      <div>
        <dt>{t("facets")}</dt>
        <dd>{facetsOf(detail.summary).join(", ") || t("none")}</dd>
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

function matchesFilter(page: PageSummary, filter: PageFilter) {
  if (filter.type === "all") return true;
  if (filter.type === "role") return filter.value === "source_digest" ? isSourceDigestPage(page) : page.role === filter.value;
  if (filter.type === "kind") return pageKindOf(page) === filter.value;
  return facetsOf(page).includes(filter.value);
}

function pageKindOf(page: PageSummary) {
  return page.page_kind || page.page_type || page.directory || "page";
}

function facetsOf(page: PageSummary) {
  return page.facets || [];
}

function isSourceDigestPage(page: PageSummary) {
  return page.role === "source_digest" || page.page_kind === "source_digest" || page.page_type === "source" || page.directory === "sources";
}

function labelForPageKind(value: string) {
  return value.replace(/_/g, " ");
}

function labelForFacet(value: string) {
  return value.replace(/_/g, " ");
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
