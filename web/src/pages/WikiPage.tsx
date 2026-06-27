import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deletePage, getPage, updatePage, type PageDetail, type PageSummary } from "../api/client";
import type { AppContext } from "../App";
import { AsyncMarkdownPreview } from "../components/AsyncMarkdownPreview";
import { DelayedTooltip } from "../components/DelayedTooltip";
import { LoadingBlock } from "../components/LoadingBlock";
import { queryKeys } from "../queryKeys";

type Props = {
  context: AppContext;
  focusedPagePath?: string | null;
};

export function WikiPage({ context, focusedPagePath = null }: Props) {
  const [selectedPath, setSelectedPath] = useState<string | null>(focusedPagePath);
  const [selectedDetail, setSelectedDetail] = useState<PageDetail | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [deleteConfirming, setDeleteConfirming] = useState(false);

  const queryClient = useQueryClient();
  const vaultId = context.activeVaultId || "default";

  const editMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPath || !editContent.trim()) throw new Error("No page selected or content empty");
      return updatePage(context.activeVaultSelector, selectedPath, editContent);
    },
    onSuccess: (detail) => {
      setSelectedDetail(detail);
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.pages(vaultId) });
      context.setNotice({ message: `Page saved: ${detail.path}` });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPath) throw new Error("No page selected");
      return deletePage(context.activeVaultSelector, selectedPath);
    },
    onSuccess: (result) => {
      setDeleteConfirming(false);
      setSelectedPath(null);
      setSelectedDetail(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.pages(vaultId) });
      context.setNotice({ message: `Page archived: ${result.path}` });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const wikiPages = useMemo(() => context.pages.filter((page) => !isSourceDigestPage(page)), [context.pages]);

  const filteredPages = useMemo(() => {
    const query = search.trim().toLowerCase();
    return wikiPages.filter((page) => {
      if (!query) return true;
      return `${page.title} ${page.path} ${page.summary} ${page.entities.join(" ")}`.toLowerCase().includes(query);
    });
  }, [search, wikiPages]);

  const relatedPages = useMemo(() => {
    if (!selectedDetail) return [];
    return relatedPagesByEntities(selectedDetail, wikiPages);
  }, [selectedDetail, wikiPages]);

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
                <button className="button secondary" type="button" onClick={() => { setEditContent(selectedDetail.content); setEditing(true); }}>Edit</button>
                <button className="button danger" type="button" onClick={() => setDeleteConfirming(true)}>Delete</button>
              </div>
            )}
          </div>
          {loading && <LoadingBlock title={context.t("wikiPageLoading")} copy={context.t("wikiPageLoadingCopy")} />}
          {!loading && selectedDetail ? (
            <>
              <WikiStructuredPreview detail={selectedDetail} context={context} />
              <RelatedPagesSection title={context.t("relatedWikiPages")} pages={relatedPages} onOpen={context.openWikiPage} emptyText={context.t("none")} />
            </>
          ) : (
            !loading && <p className="panel-copy">{context.t("wikiNoSelection")}</p>
          )}
        </aside>
      </div>

      {editing && selectedDetail && (
        <div className="settings-modal-backdrop" onClick={() => setEditing(false)}>
          <section className="settings-modal wiki-edit-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <header className="settings-modal-header">
              <h2>Edit: {selectedDetail.summary.title}</h2>
              <button className="icon-button subtle settings-modal-close" type="button" onClick={() => setEditing(false)}>✕</button>
            </header>
            <div className="settings-modal-content wiki-edit-content">
              <textarea
                className="wiki-page-editor"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                spellCheck={false}
              />
            </div>
            <div className="wiki-edit-actions">
              <button className="button secondary" type="button" onClick={() => setEditing(false)}>Cancel</button>
              <button
                className="button primary"
                type="button"
                disabled={editMutation.isPending || !editContent.trim()}
                onClick={() => editMutation.mutate()}
              >
                {editMutation.isPending ? "Saving..." : "Save"}
              </button>
            </div>
          </section>
        </div>
      )}

      {deleteConfirming && selectedDetail && (
        <div className="settings-modal-backdrop" onClick={() => setDeleteConfirming(false)}>
          <section className="settings-modal wiki-delete-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <header className="settings-modal-header">
              <h2>Archive Page</h2>
              <button className="icon-button subtle settings-modal-close" type="button" onClick={() => setDeleteConfirming(false)}>✕</button>
            </header>
            <div className="settings-modal-content">
              <p>Archive <strong>{selectedDetail.path}</strong> to deleted_pages? The page can be restored from the maintenance directory.</p>
            </div>
            <div className="wiki-edit-actions">
              <button className="button secondary" type="button" onClick={() => setDeleteConfirming(false)}>Cancel</button>
              <button
                className="button danger"
                type="button"
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate()}
              >
                {deleteMutation.isPending ? "Archiving..." : "Archive"}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

function WikiPageRow({ page, active, onClick }: { page: PageSummary; active: boolean; onClick: () => void }) {
  return (
    <button className={`page-row ${active ? "active" : ""}`} onClick={onClick} type="button">
      <span className="page-row-heading">
        <DelayedTooltip text={page.title} className="page-row-title" />
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

type RelatedPage = {
  page: PageSummary;
  sharedEntities: string[];
};

function relatedPagesByEntities(detail: PageDetail, pages: PageSummary[]): RelatedPage[] {
  const currentEntities = pageEntitySet(detail);
  if (!currentEntities.size) return [];
  return pages
    .filter((page) => page.path !== detail.path)
    .map((page) => {
      const sharedEntities = page.entities
        .map(normalizeEntity)
        .filter((entity) => entity && currentEntities.has(entity));
      return { page, sharedEntities: uniqueStrings(sharedEntities) };
    })
    .filter((item) => item.sharedEntities.length)
    .sort((left, right) => {
      if (right.sharedEntities.length !== left.sharedEntities.length) return right.sharedEntities.length - left.sharedEntities.length;
      return left.page.title.localeCompare(right.page.title);
    })
    .slice(0, 8);
}

function pageEntitySet(detail: PageDetail) {
  const entities = new Set<string>();
  for (const entity of detail.summary.entities || []) {
    const normalized = normalizeEntity(entity);
    if (normalized) entities.add(normalized);
  }
  for (const section of extractWikiSections(detail.content)) {
    if (!["claims", "entities", "relations"].includes(section.key)) continue;
    for (const match of section.content.matchAll(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]/g)) {
      const normalized = normalizeEntity(match[1]);
      if (normalized) entities.add(normalized);
    }
  }
  return entities;
}

function normalizeEntity(value: string) {
  return value
    .replace(/^\[\[/, "")
    .replace(/\]\]$/, "")
    .split("|")
    .pop()
    ?.trim()
    .toLowerCase() || "";
}

function WikiStructuredPreview({ detail, context }: { detail: PageDetail; context: AppContext }) {
  const sections = extractWikiSections(detail.content);
  if (!sections.length) {
    return <AsyncMarkdownPreview content={detail.content} className="wiki-markdown-preview" stripFrontmatter onOpenWikiPage={context.openWikiPage} vaultPath={context.vaultPath} />;
  }
  const ordered = orderWikiSections(sections);
  return (
    <div className="wiki-structured-preview">
      {ordered.map((section) => (
        <section className={`wiki-structure-card wiki-structure-${section.key}`} key={section.key}>
          <div className="wiki-structure-heading">
            <span>{wikiSectionLabel(section.key, section.title, context.language)}</span>
          </div>
          <WikiSectionContent section={section} context={context} />
        </section>
      ))}
    </div>
  );
}

function WikiSectionContent({ section, context }: { section: WikiSection; context: AppContext }) {
  if (section.key === "relations" || section.key === "evidence" || section.key === "attachments") {
    const table = parseMarkdownTable(section.content);
    if (table) {
      return (
        <div className={`wiki-structured-table-wrap wiki-${section.key}-table-wrap`}>
          <table className={`wiki-structured-table wiki-${section.key}-table`}>
            <thead>
              <tr>
                {table.headers.map((header) => <th key={header}>{plainCellText(header)}</th>)}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, rowIndex) => (
                <tr key={`${section.key}-${rowIndex}`}>
                  {table.headers.map((_header, cellIndex) => (
                    <td key={cellIndex}>{plainCellText(row[cellIndex] || "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
  }
  return (
    <AsyncMarkdownPreview
      content={section.content}
      className="wiki-markdown-preview wiki-section-markdown"
      onOpenWikiPage={context.openWikiPage}
      vaultPath={context.vaultPath}
    />
  );
}

function parseMarkdownTable(content: string): { headers: string[]; rows: string[][] } | null {
  const lines = content.split("\n").map((line) => line.trim()).filter(Boolean);
  const headerIndex = lines.findIndex((line, index) => line.startsWith("|") && lines[index + 1]?.startsWith("|") && /^\|?\s*:?-{3,}/.test(lines[index + 1]));
  if (headerIndex < 0) return null;
  const headers = splitMarkdownTableRow(lines[headerIndex]);
  const rows = lines.slice(headerIndex + 2).filter((line) => line.startsWith("|")).map(splitMarkdownTableRow);
  return headers.length && rows.length ? { headers, rows } : null;
}

function splitMarkdownTableRow(line: string) {
  return line.replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
}

function plainCellText(value: string) {
  return value
    .replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g, (_match, target: string, alias: string | undefined) => alias || target)
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/^#+\s*/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function uniqueStrings(values: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

function isSourceDigestPage(page: PageSummary) {
  return page.role === "source_digest" || page.directory === "sources";
}

function RelatedPagesSection({
  title,
  pages,
  onOpen,
  emptyText,
}: {
  title: string;
  pages: RelatedPage[];
  onOpen: (path: string) => void;
  emptyText: string;
}) {
  return (
    <section className="wiki-link-section">
      <h3>{title}</h3>
      {pages.length ? (
        <div className="wiki-related-page-list">
          {pages.map(({ page, sharedEntities }) => (
            <button className="wiki-related-page" type="button" key={page.path} onClick={() => onOpen(page.path)}>
              <strong>{page.title}</strong>
              <code>{page.path}</code>
              <small>{sharedEntities.slice(0, 4).join(" / ")}</small>
            </button>
          ))}
        </div>
      ) : (
        <p className="panel-copy">{emptyText}</p>
      )}
    </section>
  );
}

type WikiSection = {
  key: string;
  title: string;
  content: string;
  index: number;
};

const WIKI_SECTION_ORDER = ["summary", "claims", "relations", "synthesis", "entities", "evidence", "attachments"];

function extractWikiSections(content: string): WikiSection[] {
  const body = stripPageChrome(content);
  const matches = Array.from(body.matchAll(/^##\s+(.+?)\s*$/gm));
  if (!matches.length) return [];
  return matches.map((match, index) => {
    const title = match[1].trim();
    const start = (match.index || 0) + match[0].length;
    const end = matches[index + 1]?.index ?? body.length;
    return {
      key: normalizeSectionKey(title),
      title,
      content: body.slice(start, end).trim(),
      index,
    };
  }).filter((section) => section.content);
}

function stripPageChrome(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/^# .+?\n+---\s*\n[\s\S]*?\n---\s*\n?/, "")
    .replace(/^---\s*\n[\s\S]*?\n---\s*\n?/, "")
    .replace(/^# .+?\n+/, "")
    .trim();
}

function normalizeSectionKey(title: string) {
  return title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function orderWikiSections(sections: WikiSection[]) {
  return [...sections].sort((left, right) => {
    const leftIndex = WIKI_SECTION_ORDER.indexOf(left.key);
    const rightIndex = WIKI_SECTION_ORDER.indexOf(right.key);
    if (leftIndex === -1 && rightIndex === -1) return left.index - right.index;
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
}

function wikiSectionLabel(key: string, title: string, language: AppContext["language"]) {
  if (language !== "zh") return title;
  const labels: Record<string, string> = {
    summary: "摘要",
    claims: "核心断言",
    relations: "关系三元组",
    synthesis: "综合说明",
    entities: "实体",
    evidence: "证据",
    attachments: "附件",
  };
  return labels[key] || title;
}
