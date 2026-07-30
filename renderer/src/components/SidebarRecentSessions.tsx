import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import { deleteChatSession, ingestChatSession, listAllChatSessions, updateChatSession, type ChatSessionSummary, type VaultSelector } from "../api/client";
import type { SidebarAppContext } from "../appContext";
import { queryKeys } from "../queryKeys";
import { userFacingError } from "../userFacingError";
import { ChatIngestTargetModal } from "./ChatIngestTargetModal";
import { DeleteConfirmationDialog } from "./DeleteConfirmationDialog";
import { LineIcon } from "./LineIcon";

type Props = {
  context: SidebarAppContext;
};

export function SidebarRecentSessions({ context }: Props) {
  const queryClient = useQueryClient();
  const [collapsedVaults, setCollapsedVaults] = useState<Set<string>>(() => new Set());
  const vaults = context.vaultOptions.filter((vault) => !vault.virtual);
  const vaultKey = vaults.map((vault) => `${vault.id}:${vault.path}`).join("|");
  const enabled = context.configExists && vaults.length > 0;
  const sessionsQuery = useQuery({
    queryKey: queryKeys.sidebarChatSessions(context.configPath, vaultKey),
    queryFn: async () => {
      const requests: Array<Promise<ChatSessionSummary[]>> = [
        listAllChatSessions(globalVaultSelectorFor(context))
          .then((response) =>
            (response.sessions || []).map((session) => ({
              ...session,
              vault_id: "all",
              vault_name: context.t("allVaults"),
              vault_path: "",
            })),
          ),
        ...vaults.map((vault) =>
          listAllChatSessions(vaultSelectorFor(context, vault))
            .then((response) =>
              (response.sessions || []).map((session) => ({
                ...session,
                vault_id: session.vault_id || vault.id,
                vault_name: session.vault_name || vault.name,
                vault_path: session.vault_path || vault.path,
              })),
            ),
        ),
      ];
      const results = await Promise.allSettled(requests);
      const successful = results.filter(
        (result): result is PromiseFulfilledResult<ChatSessionSummary[]> => result.status === "fulfilled",
      );
      if (!successful.length) {
        const failure = results.find(
          (result): result is PromiseRejectedResult => result.status === "rejected",
        );
        throw failure?.reason ?? new Error("Chat session requests failed.");
      }
      return {
        failedScopeCount: results.length - successful.length,
        sessions: sortSessions(successful.flatMap((result) => result.value)),
      };
    },
    enabled,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });

  const invalidateSessions = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.sidebarChatSessions(context.configPath, vaultKey) });
  };

  const sessions = sessionsQuery.data?.sessions || [];
  const isLoading = sessionsQuery.isLoading;
  const failedScopeCount = sessionsQuery.data?.failedScopeCount || 0;
  const loadError = sessionsQuery.isError
    ? userFacingError(sessionsQuery.error, context.language)
    : failedScopeCount
      ? context.language === "zh"
        ? `有 ${failedScopeCount} 个知识库的历史会话暂时无法读取。`
        : `${failedScopeCount} knowledge base history group(s) could not be loaded.`
      : "";
  const grouped = groupChatSessions(sessions, vaults);
  const globalSessions = sortSessions(sessions.filter((session) => session.vault_id === "all"));

  return (
    <aside className="chat-session-sidebar sidebar-recent-sessions">
      <div className="chat-session-list" aria-busy={isLoading}>
        {isLoading && <span className="chat-session-muted">{context.t("loading")}</span>}
        {loadError && (
          <div className="chat-session-load-error" role="alert">
            <span>{loadError}</span>
            <button type="button" onClick={() => void sessionsQuery.refetch()}>
              {context.language === "zh" ? "重试" : "Retry"}
            </button>
          </div>
        )}
        {grouped.map((group) => (
          <section className="chat-session-folder" key={group.key}>
            <div className="chat-session-folder-header">
              <button
                className="chat-session-folder-toggle"
                type="button"
                aria-expanded={!collapsedVaults.has(group.key)}
                onClick={() => setCollapsedVaults((current) => toggledSet(current, group.key))}
              >
                <LineIcon name="wiki" />
                <span>{group.label}</span>
              </button>
              {!!group.sessions.length && <em>{group.sessions.length}</em>}
              <button className="chat-vault-new-button" type="button" onClick={() => context.openChatSession(null, group.key)} title={context.t("chatNewSession")} aria-label={`${group.label} · ${context.t("chatNewSession")}`}><Plus aria-hidden="true" /></button>
            </div>
            {!collapsedVaults.has(group.key) && <div className="chat-session-folder-list">
              {group.sessions.map((session) => (
                <SessionButton session={session} context={context} key={session.session_id} onInvalidate={invalidateSessions} />
              ))}
            </div>}
          </section>
        ))}
        {!!globalSessions.length && (
          <section className="chat-session-folder global-chat-group">
            <div className="chat-session-folder-header">
              <button
                className="chat-session-folder-toggle"
                type="button"
                aria-expanded={!collapsedVaults.has("all")}
                onClick={() => setCollapsedVaults((current) => toggledSet(current, "all"))}
              >
                <LineIcon name="wiki" />
                <span>{context.t("chatGlobal")}</span>
              </button>
              <em>{globalSessions.length}</em>
              <button className="chat-vault-new-button" type="button" onClick={() => context.openChatSession(null, "all")} title={context.t("chatNewSession")} aria-label={`${context.t("chatGlobal")} · ${context.t("chatNewSession")}`}><Plus aria-hidden="true" /></button>
            </div>
            {!collapsedVaults.has("all") && <div className="chat-session-folder-list">
              {globalSessions.map((session) => (
                <SessionButton session={session} context={context} key={`${session.vault_id || "global"}:${session.session_id}`} onInvalidate={invalidateSessions} />
              ))}
            </div>}
          </section>
        )}
      </div>
    </aside>
  );
}

function SessionButton({ session, context, onInvalidate }: { session: ChatSessionSummary; context: SidebarAppContext; onInvalidate: () => void }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [ingestTitle, setIngestTitle] = useState(session.title || "");
  const [ingestTargetVaultId, setIngestTargetVaultId] = useState(defaultTargetVaultId(context, session));
  const [ingesting, setIngesting] = useState(false);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const selector: VaultSelector = {
    config_path: context.configPath,
    vault_id: session.vault_id,
    vault_path: session.vault_path ?? undefined,
  };

  useEffect(() => {
    if (!menuOpen) return;
    function close() { setMenuOpen(false); }
    function onKeyDown(e: KeyboardEvent) { if (e.key === "Escape") close(); }
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) close();
    }
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  async function handleDelete() {
    setMenuOpen(false);
    setDeleteError(null);
    setDeleteConfirming(true);
  }

  async function confirmDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteChatSession(selector, session.session_id, session.session_revision);
      setDeleteConfirming(false);
      onInvalidate();
    } catch (error) {
      setDeleteError(userFacingError(error, context.language));
    } finally {
      setDeleting(false);
    }
  }

  async function handleIngest() {
    setMenuOpen(false);
    setIngestTitle(session.title || "");
    setIngestTargetVaultId(defaultTargetVaultId(context, session));
    setIngestOpen(true);
  }

  async function confirmIngest() {
    const targetVaultId = ingestTargetVaultId || defaultTargetVaultId(context, session);
    if (!targetVaultId || !ingestTitle.trim()) return;
    setIngesting(true);
    try {
      const response = await ingestChatSession(selector, session.session_id, {
        expected_session_revision: session.session_revision,
        source_title: ingestTitle.trim(),
        target_vault_id: targetVaultId,
      });
      await context.refreshAll();
      if (response.run_id) context.openRun(response.run_id, targetVaultId, response.flow);
      else context.navigate("ingest");
      setIngestOpen(false);
    } catch (error) {
      console.error("Chat session ingest failed", error);
    } finally {
      setIngesting(false);
    }
  }

  function handleRename() {
    setMenuOpen(false);
    const title = window.prompt(
      context.language === "zh" ? `重命名会话 "${session.title}"：` : `Rename session "${session.title}":`,
      session.title,
    );
    if (!title || title === session.title) return;
    updateChatSession(selector, session.session_id, title, session.session_revision).then(onInvalidate).catch((error) => {
      console.error("Chat session rename failed", error);
    });
  }

  return (
    <>
      <div className="chat-session-row compact">
        <button className="chat-session-open-button" type="button" onClick={() => context.openChatSession(session.session_id, session.vault_id)} title={session.title}>
          <span className="chat-session-title">{session.title}</span>
        </button>
        <div className="chat-session-menu" ref={menuRef}>
          <button type="button" className="chat-session-menu-trigger" onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }} aria-label="Session menu">···</button>
          {menuOpen && (
            <div className="chat-session-menu-popover">
              <button type="button" onClick={handleIngest}>{context.language === "zh" ? "导入" : "Import"}</button>
              <button type="button" onClick={handleRename}>{context.language === "zh" ? "重命名" : "Rename"}</button>
              <button className="danger" type="button" onClick={handleDelete}>{context.language === "zh" ? "删除" : "Delete"}</button>
            </div>
          )}
        </div>
      </div>
      <ChatIngestTargetModal
        context={context}
        isOpen={ingestOpen}
        title={ingestTitle}
        targetVaultId={ingestTargetVaultId}
        submitting={ingesting}
        onTitleChange={setIngestTitle}
        onTargetVaultChange={setIngestTargetVaultId}
        onCancel={() => !ingesting && setIngestOpen(false)}
        onConfirm={() => void confirmIngest()}
      />
      <DeleteConfirmationDialog
        cancelLabel={context.t("cancel")}
        closeLabel={context.t("close")}
        confirmLabel={context.language === "zh" ? "删除" : "Delete"}
        error={deleteError}
        isOpen={deleteConfirming}
        pending={deleting}
        pendingLabel={context.language === "zh" ? "正在删除..." : "Deleting..."}
        title={context.language === "zh" ? "删除会话" : "Delete session"}
        onCancel={() => {
          if (deleting) return;
          setDeleteConfirming(false);
          setDeleteError(null);
        }}
        onConfirm={() => void confirmDelete()}
      >
        <p>
          {context.language === "zh"
            ? <>删除会话 <strong>{session.title}</strong>？该会话及其全部消息都会一并删除。</>
            : <>Delete session <strong>{session.title}</strong>? The conversation and all of its messages will be removed.</>}
        </p>
      </DeleteConfirmationDialog>
    </>
  );
}

function defaultTargetVaultId(context: SidebarAppContext, session?: ChatSessionSummary): string {
  if (session?.vault_id && session.vault_id !== "all" && context.vaultOptions.some((vault) => !vault.virtual && vault.id === session.vault_id)) {
    return session.vault_id;
  }
  if (context.activeVaultId !== "all" && context.vaultOptions.some((vault) => !vault.virtual && vault.id === context.activeVaultId)) {
    return context.activeVaultId;
  }
  return context.vaultOptions.find((vault) => !vault.virtual)?.id || "";
}

function groupChatSessions(sessions: ChatSessionSummary[], vaults: Array<{ id: string; name: string }>) {
  const groups = new Map(vaults.map((vault) => [vault.id, { key: vault.id, label: vault.name, sessions: [] as ChatSessionSummary[] }]));
  for (const session of sessions) {
    if (session.vault_id === "all") continue;
    if (session.vault_id) groups.get(session.vault_id)?.sessions.push(session);
  }
  return Array.from(groups.values()).sort((left, right) => {
    if (left.key === "general") return -1;
    if (right.key === "general") return 1;
    return left.label.localeCompare(right.label);
  });
}

function sortSessions(sessions: ChatSessionSummary[]) {
  return [...sessions].sort((left, right) => Date.parse(right.updated_at || "") - Date.parse(left.updated_at || ""));
}

function toggledSet(current: Set<string>, key: string): Set<string> {
  const next = new Set(current);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

function vaultSelectorFor(context: SidebarAppContext, vault: { id: string; path: string }): VaultSelector {
  return {
    config_path: context.configPath,
    vault_id: vault.id,
    vault_path: vault.path,
  };
}

function globalVaultSelectorFor(context: SidebarAppContext): VaultSelector {
  return {
    config_path: context.configPath,
    vault_id: "all",
  };
}
