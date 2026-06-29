import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteChatSession, ingestChatSession, listChatSessions, updateChatSession, type ChatSessionSummary, type VaultSelector } from "../api/client";
import type { AppContext } from "../appContext";
import { LineIcon } from "./LineIcon";

const RECENT_SESSION_LIMIT = 80;

type Props = {
  context: AppContext;
};

export function SidebarRecentSessions({ context }: Props) {
  const queryClient = useQueryClient();
  const vaults = context.vaultOptions.filter((vault) => !vault.virtual);
  const vaultKey = vaults.map((vault) => `${vault.id}:${vault.path}`).join("|");
  const enabled = context.configExists && vaults.length > 0;
  const sessionsQuery = useQuery({
    queryKey: ["sidebar-chat-sessions", context.configPath, vaultKey],
    queryFn: async () => {
      const scoped = vaults.map((vault) =>
          listChatSessions(vaultSelectorFor(context, vault), RECENT_SESSION_LIMIT)
            .then((response) =>
              (response.sessions || []).map((session) => ({
                ...session,
                vault_id: session.vault_id || vault.id,
                vault_name: session.vault_name || vault.name,
                vault_path: session.vault_path || vault.path,
              })),
            )
            .catch(() => []),
        );
      const results = await Promise.all([
        listChatSessions(globalVaultSelectorFor(context), RECENT_SESSION_LIMIT)
          .then((response) =>
            (response.sessions || []).map((session) => ({
              ...session,
              vault_id: "all",
              vault_name: context.t("allVaults"),
              vault_path: "",
            })),
          )
          .catch(() => []),
        ...scoped,
      ]);
      return sortSessions(results.flat()).slice(0, RECENT_SESSION_LIMIT * Math.max(1, vaults.length + 1));
    },
    enabled,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });

  const invalidateSessions = () => {
    queryClient.invalidateQueries({ queryKey: ["sidebar-chat-sessions", context.configPath, vaultKey] });
  };

  const sessions = sessionsQuery.data || [];
  const isLoading = sessionsQuery.isLoading;
  const grouped = groupChatSessions(sessions, context);
  const globalSessions = sortSessions(sessions.filter((session) => session.vault_id === "all")).slice(0, 18);

  return (
    <aside className="chat-session-sidebar sidebar-recent-sessions">
      <div className="chat-session-sidebar-header">
        <span>
          <strong>{context.t("knowledgeBases")}</strong>
          <small>{sessions.length ? `${sessions.length} ${context.t("chatSessions").toLowerCase()}` : context.t("chatNoSessions")}</small>
        </span>
        <button className="icon-button chat-new-button" type="button" onClick={() => context.openChatSession(null, context.activeVaultId === "all" ? vaults[0]?.id : context.activeVaultId)} title={context.t("chatNewSession")} aria-label={context.t("chatNewSession")}>
          +
        </button>
      </div>
      <div className="chat-session-list" aria-busy={isLoading}>
        {isLoading && <span className="chat-session-muted">{context.t("loading")}</span>}
        {!isLoading && sessions.length === 0 && <span className="chat-session-muted">{context.t("chatNoSessions")}</span>}
        {grouped.map((group) => (
          <details className="chat-session-folder" key={group.key} open={group.key === context.activeVaultId}>
            <summary>
              <LineIcon name="wiki" />
              <span>{group.label}</span>
              <em>{group.sessions.length}</em>
            </summary>
            <div className="chat-session-folder-list">
              {group.sessions.slice(0, 8).map((session) => (
                <SessionButton session={session} context={context} key={session.session_id} onInvalidate={invalidateSessions} />
              ))}
            </div>
          </details>
        ))}
        {!!globalSessions.length && (
          <section className="chat-session-group global-chat-group">
            <h3>{context.t("chatGlobal")}</h3>
            {globalSessions.map((session) => (
              <SessionButton session={session} context={context} key={`${session.vault_id || "global"}:${session.session_id}`} onInvalidate={invalidateSessions} />
            ))}
          </section>
        )}
      </div>
    </aside>
  );
}

function SessionButton({ session, context, onInvalidate }: { session: ChatSessionSummary; context: AppContext; onInvalidate: () => void }) {
  const [menuOpen, setMenuOpen] = useState(false);
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
    if (!window.confirm(context.language === "zh" ? `确认删除会话 "${session.title}"？` : `Delete session "${session.title}"?`)) return;
    try {
      await deleteChatSession(selector, session.session_id);
      onInvalidate();
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }

  async function handleIngest() {
    setMenuOpen(false);
    try {
      const response = await ingestChatSession(selector, session.session_id);
      context.setNotice({
        message: response.run_id ? `${context.t("chatExcerptQueued")} ${response.run_id}` : context.t("chatExcerptQueued"),
        actionLabel: context.t("viewRun"),
        onAction: () => context.navigate("runs"),
      });
      await context.refreshAll();
      context.navigate("runs");
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }

  function handleRename() {
    setMenuOpen(false);
    const title = window.prompt(
      context.language === "zh" ? `重命名会话 "${session.title}"：` : `Rename session "${session.title}":`,
      session.title,
    );
    if (!title || title === session.title) return;
    updateChatSession(selector, session.session_id, title).then(onInvalidate).catch((error) => {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    });
  }

  return (
    <div className="chat-session-row compact">
      <button type="button" onClick={() => context.openChatSession(session.session_id, session.vault_id)} title={session.title}>
        <span className="chat-session-title">{session.title}</span>
      </button>
      <div className="chat-session-menu" ref={menuRef}>
        <button type="button" className="chat-session-menu-trigger" onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }} aria-label="Session menu">···</button>
        {menuOpen && (
          <div className="chat-session-menu-popover">
            <button type="button" onClick={handleIngest}>{context.language === "zh" ? "编译" : "Compile"}</button>
            <button type="button" onClick={handleRename}>{context.language === "zh" ? "重命名" : "Rename"}</button>
            <button className="danger" type="button" onClick={handleDelete}>{context.language === "zh" ? "删除" : "Delete"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

function groupChatSessions(sessions: ChatSessionSummary[], context: AppContext) {
  const groups = new Map<string, { key: string; label: string; sessions: ChatSessionSummary[] }>();
  for (const session of sessions) {
    if (session.vault_id === "all") continue;
    const key = session.vault_id || "general";
    const label = session.vault_name || (session.vault_id ? session.vault_id : context.t("chatGroupGeneral"));
    if (!groups.has(key)) {
      groups.set(key, { key, label, sessions: [] });
    }
    groups.get(key)?.sessions.push(session);
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

function vaultSelectorFor(context: AppContext, vault: { id: string; path: string }): VaultSelector {
  return {
    config_path: context.configPath,
    vault_id: vault.id,
    vault_path: vault.path,
  };
}

function globalVaultSelectorFor(context: AppContext): VaultSelector {
  return {
    config_path: context.configPath,
    vault_id: "all",
  };
}
