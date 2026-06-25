import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listChatSessions, type ChatSessionSummary, type VaultSelector } from "../api/client";
import type { AppContext } from "../App";
import { LineIcon } from "./LineIcon";

const RECENT_SESSION_LIMIT = 80;

type Props = {
  context: AppContext;
};

export function SidebarRecentSessions({ context }: Props) {
  const vaults = context.vaultOptions.filter((vault) => !vault.virtual);
  const vaultKey = vaults.map((vault) => `${vault.id}:${vault.path}`).join("|");
  const enabled = context.configExists && vaults.length > 0;
  const sessionsQuery = useQuery({
    queryKey: ["sidebar-chat-sessions", context.configPath, vaultKey],
    queryFn: async () => {
      const results = await Promise.all(
      vaults.map((vault) =>
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
      ),
      );
      return sortSessions(results.flat()).slice(0, RECENT_SESSION_LIMIT * Math.max(1, vaults.length));
    },
    enabled,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });

  const sessions = sessionsQuery.data || [];
  const isLoading = sessionsQuery.isLoading;
  const grouped = groupChatSessions(sessions, context);
  const globalSessions = sortSessions(sessions).slice(0, 18);

  return (
    <aside className="chat-session-sidebar sidebar-recent-sessions">
      <div className="chat-session-sidebar-header">
        <span>
          <strong>{context.t("knowledgeBases")}</strong>
          <small>{sessions.length ? `${sessions.length} ${context.t("chatSessions").toLowerCase()}` : context.t("chatNoSessions")}</small>
        </span>
        <button className="icon-button chat-new-button" type="button" onClick={() => context.openChatSession(null)} title={context.t("chatNewSession")} aria-label={context.t("chatNewSession")}>
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
                <SessionButton session={session} context={context} key={session.session_id} />
              ))}
            </div>
          </details>
        ))}
        {!!globalSessions.length && (
          <section className="chat-session-group global-chat-group">
            <h3>{context.t("chatGlobal")}</h3>
            {globalSessions.map((session) => (
              <SessionButton session={session} context={context} key={`${session.vault_id || "global"}:${session.session_id}`} />
            ))}
          </section>
        )}
      </div>
    </aside>
  );
}

function SessionButton({ session, context }: { session: ChatSessionSummary; context: AppContext }) {
  return (
    <div className="chat-session-row compact">
      <button type="button" onClick={() => context.openChatSession(session.session_id, session.vault_id)} title={session.title}>
        <span className="chat-session-title">{session.title}</span>
      </button>
    </div>
  );
}

function groupChatSessions(sessions: ChatSessionSummary[], context: AppContext) {
  const groups = new Map<string, { key: string; label: string; sessions: ChatSessionSummary[] }>();
  for (const session of sessions) {
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
