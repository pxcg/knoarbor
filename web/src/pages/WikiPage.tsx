import { useEffect, useMemo, useState } from "react";

import { getPage, getPages, type PageDetail, type PageLink, type PageSummary } from "../api/client";
import type { AppContext } from "../App";
import { AsyncMarkdownPreview } from "../components/AsyncMarkdownPreview";
import { DelayedTooltip } from "../components/DelayedTooltip";

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
  const [activeVaultPath, setActiveVaultPath] = useState(context.vaultPath);
  const [vaultPages, setVaultPages] = useState<PageSummary[]>(context.pages);
  const [pagesLoading, setPagesLoading] = useState(false);
  const vaultOptions = useMemo(() => configuredVaultOptions(context), [context.summary.vaults, context.summary.project_name, context.vaultPath]);

  const directoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const page of vaultPages) {
      counts.set(page.directory, (counts.get(page.directory) || 0) + 1);
    }
    return counts;
  }, [vaultPages]);

  const filteredPages = useMemo(() => {
    const query = search.trim().toLowerCase();
    return vaultPages.filter((page) => {
      if (directory && page.directory !== directory) return false;
      if (!query) return true;
      return `${page.title} ${page.path} ${page.summary} ${page.tags.join(" ")}`.toLowerCase().includes(query);
    });
  }, [vaultPages, directory, search]);

  useEffect(() => {
    setActiveVaultPath(context.vaultPath);
    setVaultPages(context.pages);
  }, [context.vaultPath]);

  useEffect(() => {
    let cancelled = false;
    if (activeVaultPath === context.vaultPath) {
      setVaultPages(context.pages);
      return;
    }
    setPagesLoading(true);
    getPages(activeVaultPath)
      .then((response) => {
        if (!cancelled) setVaultPages(response.pages);
      })
      .catch((error) => {
        if (!cancelled) context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      })
      .finally(() => {
        if (!cancelled) setPagesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeVaultPath, context.pages, context.setNotice, context.vaultPath]);

  useEffect(() => {
    if (focusedPagePath) setSelectedPath(focusedPagePath);
  }, [focusedPagePath]);

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
    getPage(activeVaultPath, selectedPath)
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
  }, [activeVaultPath, context.setNotice, selectedPath]);

  return (
    <section className="view active">
      <div className="wiki-workspace">
        <aside className="panel wiki-directory-panel">
          <div className="panel-header compact">
            <h2>{context.t("wikiDirectory")}</h2>
          </div>
          <div className="wiki-directory-section">
            <label className="field compact-field">
              <span>{context.t("activeVault")}</span>
              <select value={activeVaultPath} onChange={(event) => setActiveVaultPath(event.target.value)}>
                {vaultOptions.map((vault) => (
                  <option key={vault.path} value={vault.path}>
                    {vault.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="wiki-directory-section">
            <button className={`wiki-directory-row ${directory === "" ? "active" : ""}`} onClick={() => setDirectory("")} type="button">
              <span>{context.t("allPages")}</span>
              <strong>{vaultPages.length}</strong>
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
            <span className="pill">{pagesLoading ? context.t("loading") : `${filteredPages.length} ${context.t("pages")}`}</span>
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
            {selectedDetail && activeVaultPath === context.vaultPath && (
              <button className="button secondary" type="button" onClick={() => context.openPageInGraph(selectedDetail.path)}>{context.t("openInGraph")}</button>
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

function configuredVaultOptions(context: AppContext) {
  const configured = context.summary.vaults?.filter((vault) => vault.path);
  if (configured?.length) {
    return configured.map((vault) => ({ name: vault.name || vault.id || lastPathSegment(vault.path), path: vault.path }));
  }
  const name = context.summary.project_name?.trim() || lastPathSegment(context.vaultPath) || "KnoArbor";
  return [{ name, path: context.vaultPath }];
}

function lastPathSegment(path: string) {
  const parts = path.replace(/\/+$/, "").split("/").filter(Boolean);
  return parts[parts.length - 1] || path;
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
    .filter((link) => link.path);
  return (
    <section className="wiki-link-section">
      <h3>{title}</h3>
      {resolved.length ? (
        <div className="page-path-links">
          {resolved.map((link) => (
            <button key={`${direction}:${link.path}`} onClick={() => link.path && onOpen(link.path)} type="button">
              {link.label}
            </button>
          ))}
        </div>
      ) : (
        <p className="panel-copy">{emptyText}</p>
      )}
    </section>
  );
}
