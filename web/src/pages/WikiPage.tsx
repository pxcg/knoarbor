import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deletePage, getPage, updatePage, type PageDetail, type PageSummary } from "../api/client";
import type { AppContext } from "../appContext";
import { DelayedTooltip } from "../components/DelayedTooltip";
import { LoadingBlock } from "../components/LoadingBlock";
import { queryKeys } from "../queryKeys";
import { filterWikiPages, relatedPagesByEntities, searchWikiPages, type RelatedPage } from "./wiki/WikiModel";
import { WikiStructuredPreview } from "./wiki/WikiStructuredPreview";

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

  const wikiPages = useMemo(() => filterWikiPages(context.pages), [context.pages]);
  const filteredPages = useMemo(() => searchWikiPages(wikiPages, search), [search, wikiPages]);

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
