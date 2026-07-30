import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deletePage, getPage, updatePage, updateRawPage, type PageDetail, type PageSummary, type ProjectionEdit, type ProjectionEditorState, type RawRevisionEdit } from "../api/client";
import { isApiNotFound } from "../api/http";
import type { WikiAppContext } from "../appContext";
import { DelayedTooltip } from "../components/DelayedTooltip";
import { DeleteConfirmationDialog } from "../components/DeleteConfirmationDialog";
import { LoadingBlock } from "../components/LoadingBlock";
import { AsyncMarkdownPreview } from "../components/AsyncMarkdownPreview";
import { canRevealDesktopPath, revealDesktopPath } from "../desktop/desktopBridge";
import { queryKeys } from "../queryKeys";
import { userFacingError } from "../userFacingError";
import { filterWikiPages, relatedPagesByEntities, searchWikiPages, type RelatedPage } from "./wiki/WikiModel";
import { WikiStructuredPreview } from "./wiki/WikiStructuredPreview";
import { ProjectionEditor } from "./wiki/ProjectionEditor";
import { RawRevisionEditor } from "./wiki/RawRevisionEditor";

type Props = { active: boolean; context: WikiAppContext };

export function WikiPage({ active, context }: Props) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<PageDetail | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [projectionEdit, setProjectionEdit] = useState<ProjectionEditorState | null>(null);
  const [rawEditing, setRawEditing] = useState(false);
  const [rawEditContent, setRawEditContent] = useState("");
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [highlightTerm, setHighlightTerm] = useState<string | null>(null);
  const [contentView, setContentView] = useState<"raw" | "wiki">("raw");
  const [operationError, setOperationError] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const vaultId = context.activeVaultId || "default";

  const editMutation = useMutation({
    onMutate: () => setOperationError(null),
    mutationFn: async () => {
      if (!selectedPath || !projectionEdit) throw new Error("No editable projection selected");
      const edit: ProjectionEdit = {
        schema_version: "projection_edit.v1",
        base_revision_id: projectionEdit.base_revision_id,
        synthesis: projectionEdit.synthesis,
        claims: projectionEdit.claims.map(({ id, claim }) => ({ id, claim })),
        entities: projectionEdit.entities,
        relations: projectionEdit.relations,
      };
      return updatePage(context.activeVaultSelector, selectedPath, edit);
    },
    onSuccess: (detail) => {
      setSelectedDetail(detail);
      setProjectionEdit(null);
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.pages(vaultId) });
    },
    onError: (error) => setOperationError(userFacingError(error instanceof Error ? error.message : String(error), context.language)),
  });

  const deleteMutation = useMutation({
    onMutate: () => setOperationError(null),
    mutationFn: async () => {
      if (!selectedPath) throw new Error("No page selected");
      return deletePage(context.activeVaultSelector, selectedPath);
    },
    onSuccess: (result) => {
      setDeleteConfirming(false);
      setSelectedPath(null);
      setSelectedDetail(null);
      queryClient.setQueryData(queryKeys.pages(vaultId), (current: { vault_path: string; pages: PageSummary[] } | undefined) =>
        current ? { ...current, pages: current.pages.filter((page) => page.path !== result.path) } : current,
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.pages(vaultId) });
    },
    onError: (error) => setOperationError(userFacingError(error instanceof Error ? error.message : String(error), context.language)),
  });

  const rawEditMutation = useMutation({
    onMutate: () => setOperationError(null),
    mutationFn: async () => {
      if (!selectedPath || !selectedDetail?.editable_raw) throw new Error("No editable raw material selected");
      const edit: RawRevisionEdit = {
        schema_version: "raw_revision_edit.v1",
        base_revision_id: selectedDetail.editable_raw.base_revision_id,
        content: rawEditContent,
      };
      return updateRawPage(context.activeVaultSelector, selectedPath, edit);
    },
    onSuccess: (response) => {
      setRawEditing(false);
      setRawEditContent("");
      setSelectedDetail(null);
      void context.loadVaultState(undefined, { activeRuns: true, recentRuns: true });
      if (response.run_id) context.openRun(response.run_id, context.activeVaultId, response.flow);
      else context.navigate("ingest");
    },
    onError: (error) => setOperationError(userFacingError(error instanceof Error ? error.message : String(error), context.language)),
  });

  const wikiPages = useMemo(() => filterWikiPages(context.pages), [context.pages]);
  const filteredPages = useMemo(() => searchWikiPages(wikiPages, search), [search, wikiPages]);

  const relatedPages = useMemo(() => {
    if (!selectedDetail) return [];
    return relatedPagesByEntities(selectedDetail, wikiPages);
  }, [selectedDetail, wikiPages]);

  useEffect(() => {
    if (!highlightTerm) return;
    const timer = window.setTimeout(() => setHighlightTerm(null), 3200);
    return () => window.clearTimeout(timer);
  }, [highlightTerm]);

  useEffect(() => {
    setContentView(selectedDetail?.default_view === "raw" && selectedDetail.raw_content ? "raw" : "wiki");
  }, [selectedDetail]);

  useEffect(() => {
    setSelectedDetail(null);
    setHighlightTerm(null);
    setOperationError(null);
    setSelectedPath(null);
  }, [context.activeVaultId]);

  useEffect(() => {
    if (selectedPath && filteredPages.some((page) => page.path === selectedPath)) return;
    const nextPath = filteredPages[0]?.path || null;
    if (nextPath !== selectedPath) {
      setSelectedPath(nextPath);
    }
    if (!nextPath) setSelectedDetail(null);
  }, [filteredPages, selectedPath]);

  useEffect(() => {
    if (!active) return;
    const target = context.navigationTarget;
    if (target?.kind !== "wiki-page" || target.vaultId !== context.activeVaultId) return;
    let cancelled = false;
    setLoading(true);
    setOperationError(null);
    getPage(context.activeVaultSelector, target.path)
      .then((detail) => {
        if (cancelled) return;
        setSelectedPath(detail.path);
        setSelectedDetail(detail);
      })
      .catch((error) => {
        if (cancelled) return;
        setOperationError(
          isApiNotFound(error)
            ? (context.language === "zh" ? "目标知识页面不存在或已被删除。" : "The requested knowledge page does not exist or was deleted.")
            : userFacingError(error, context.language),
        );
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        context.consumeNavigationTarget(target.requestId);
      });
    return () => {
      cancelled = true;
    };
  }, [active, context.activeVaultId, context.activeVaultSelector, context.consumeNavigationTarget, context.language, context.navigationTarget]);

  useEffect(() => {
    if (!active) return;
    const target = context.navigationTarget;
    if (target?.kind === "wiki-page" && target.vaultId === context.activeVaultId) return;
    if (!selectedPath) {
      setSelectedDetail(null);
      return;
    }
    if (selectedDetail?.path === selectedPath) return;
    let cancelled = false;
    setLoading(true);
    getPage(context.activeVaultSelector, selectedPath)
      .then((detail) => {
        if (!cancelled) setSelectedDetail(detail);
      })
      .catch((error) => {
        if (!cancelled) setOperationError(userFacingError(error instanceof Error ? error.message : String(error), context.language));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active, context.activeVaultId, context.activeVaultSelector, context.language, context.navigationTarget, selectedDetail?.path, selectedPath]);

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
                <WikiPageRow key={page.path} page={page} active={selectedPath === page.path} onClick={() => {
                  if (context.navigationTarget?.kind === "wiki-page") context.consumeNavigationTarget(context.navigationTarget.requestId);
                  setSelectedPath(page.path);
                }} />
              ))
            ) : wikiPages.length === 0 ? (
              <article className="result-item">
                <strong>{context.t("wikiEmptyTitle")}</strong>
                <p>{context.t("noPages")}</p>
              </article>
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
            </div>
            {selectedDetail && (
              <div className="wiki-preview-actions">
                <button className="button secondary" type="button" onClick={() => askAboutPage(context, selectedDetail)}>{context.t("askInChat")}</button>
                <button
                  className="button secondary"
                  type="button"
                  disabled={contentView === "wiki" && !selectedDetail.raw_content}
                  onClick={() => setContentView(contentView === "raw" ? "wiki" : "raw")}
                >
                  {contentView === "raw" ? context.t("wikiShowExtraction") : context.t("wikiShowRaw")}
                </button>
                {selectedDetail.original_source_path && canRevealDesktopPath() ? (
                  <button className="button secondary" type="button" onClick={() => void revealDesktopPath(selectedDetail.original_source_path || "")}>{context.t("showInFolder")}</button>
                ) : null}
                <button className="button secondary" type="button" onClick={() => context.openPageInGraph(selectedDetail.path)}>{context.t("openInGraph")}</button>
                {contentView === "wiki" && selectedDetail.editable_projection ? (
                  <button className="button secondary" type="button" onClick={() => { setProjectionEdit(structuredClone(selectedDetail.editable_projection!)); setEditing(true); }}>
                    {context.language === "zh" ? "编辑知识" : "Edit knowledge"}
                  </button>
                ) : null}
                {contentView === "raw" && selectedDetail.editable_raw ? (
                  <button className="button secondary" type="button" onClick={() => { setRawEditContent(selectedDetail.editable_raw!.content); setRawEditing(true); setOperationError(null); }}>
                    {context.language === "zh" ? "修订原文" : "Revise Raw"}
                  </button>
                ) : null}
                <button className="button danger" type="button" onClick={() => { setOperationError(null); setDeleteConfirming(true); }}>Delete</button>
              </div>
            )}
          </div>
          {operationError ? <p className="settings-action-note warning" role="alert">{operationError}</p> : null}
          {loading && <LoadingBlock title={context.t("wikiPageLoading")} copy={context.t("wikiPageLoadingCopy")} />}
          {!loading && selectedDetail ? (
            <>
              {contentView === "raw" && selectedDetail.raw_content ? (
                <AsyncMarkdownPreview
                  content={selectedDetail.raw_content}
                  className="wiki-markdown-preview wiki-raw-preview"
                  vaultPath={context.vaultPath}
                  highlightTerm={highlightTerm}
                  scrollToHighlight
                />
              ) : (
                <>
                  <WikiStructuredPreview
                    detail={selectedDetail}
                    context={context}
                    highlightTerm={highlightTerm}
                    onHighlightTerm={setHighlightTerm}
                    onOpenEvidence={(term) => {
                      setHighlightTerm(term);
                      setContentView("raw");
                    }}
                  />
                  <RelatedPagesSection title={context.t("relatedWikiPages")} pages={relatedPages} onOpen={context.openWikiPage} emptyText={context.t("none")} />
                </>
              )}
            </>
          ) : null}
        </aside>
      </div>

      {editing && projectionEdit ? (
        <ProjectionEditor
          edit={projectionEdit}
          error={operationError}
          language={context.language}
          pending={editMutation.isPending}
          onCancel={() => { if (!editMutation.isPending) { setEditing(false); setProjectionEdit(null); } }}
          onChange={setProjectionEdit}
          onSave={() => editMutation.mutate()}
        />
      ) : null}

      {rawEditing && selectedDetail?.editable_raw ? (
        <RawRevisionEditor
          state={selectedDetail.editable_raw}
          content={rawEditContent}
          error={operationError}
          language={context.language}
          pending={rawEditMutation.isPending}
          onCancel={() => { if (!rawEditMutation.isPending) { setRawEditing(false); setRawEditContent(""); setOperationError(null); } }}
          onChange={setRawEditContent}
          onSave={() => rawEditMutation.mutate()}
        />
      ) : null}

      <DeleteConfirmationDialog
        cancelLabel={context.t("cancel")}
        closeLabel={context.t("close")}
        confirmLabel={context.language === "zh" ? "删除" : "Delete"}
        error={deleteConfirming ? operationError : null}
        isOpen={deleteConfirming && Boolean(selectedDetail)}
        pending={deleteMutation.isPending}
        pendingLabel={context.language === "zh" ? "正在删除..." : "Deleting..."}
        title={context.language === "zh" ? "删除页面" : "Delete page"}
        onCancel={() => {
          if (deleteMutation.isPending) return;
          setDeleteConfirming(false);
          setOperationError(null);
        }}
        onConfirm={() => deleteMutation.mutate()}
      >
        {selectedDetail ? (
          <p>
            {context.language === "zh"
              ? <>删除 <strong>{selectedDetail.summary.title}</strong>？对应的原文、提取结果以及检索和图谱数据都会一并删除。</>
              : <>Delete <strong>{selectedDetail.summary.title}</strong>? Its raw material, extraction results, search data, and graph data will also be removed.</>}
          </p>
        ) : null}
      </DeleteConfirmationDialog>
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

function askAboutPage(context: WikiAppContext, detail: PageDetail) {
  const title = detail.summary.title || detail.path;
  context.openChatWithPrompt(`请基于「${title}」（${detail.path}）对应的 raw 原文材料回答，并把 Wiki 页面只作为检索定位参考。`, context.activeVaultId);
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
              <small>{sharedEntities.join(" / ")}</small>
            </button>
          ))}
        </div>
      ) : (
        <p className="panel-copy">{emptyText}</p>
      )}
    </section>
  );
}
