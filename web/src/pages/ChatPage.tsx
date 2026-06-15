import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  closeChatSession,
  deleteChatSession,
  ingestChatSession,
  listChatSessions,
  readChatSession,
  sendChatMessage,
  type ChatCitation,
  type ChatMessageItem,
  type ChatSessionSummary,
} from "../api/client";
import type { AppContext } from "../App";

type Props = {
  context: AppContext;
};

type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
};

const exampleKeys = ["chatExampleAgentLoop", "chatExampleLint", "chatExampleRag", "chatExampleReadPage"];

export function ChatPage({ context }: Props) {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [recentSessions, setRecentSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isArchiving, setIsArchiving] = useState(false);

  const apiMessages = useMemo<ChatMessageItem[]>(
    () => turns
      .filter((turn) => turn.role === "user" || turn.role === "assistant")
      .slice(-10)
      .map((turn) => ({ role: turn.role, content: turn.content })),
    [turns],
  );

  useEffect(() => {
    let cancelled = false;
    setIsLoadingSessions(true);
    listChatSessions(context.activeVaultSelector, 20)
      .then((response) => {
        if (!cancelled) setRecentSessions(response.sessions || []);
      })
      .catch(() => {
        if (!cancelled) setRecentSessions([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingSessions(false);
      });
    return () => {
      cancelled = true;
    };
  }, [context.activeVaultSelector]);

  useEffect(() => {
    const prompt = context.pendingChatPrompt.trim();
    if (!prompt) return;
    setInput(prompt);
    context.clearPendingChatPrompt();
  }, [context.pendingChatPrompt, context.clearPendingChatPrompt]);

  async function refreshSessions() {
    try {
      const response = await listChatSessions(context.activeVaultSelector, 20);
      setRecentSessions(response.sessions || []);
    } catch {
      setRecentSessions([]);
    }
  }

  function newSession() {
    if (isSending) return;
    setSessionId(null);
    setTurns([]);
    setInput("");
  }

  async function restoreSession(nextSessionId: string) {
    if (isSending) return;
    setIsSending(true);
    try {
      const record = await readChatSession(context.activeVaultSelector, nextSessionId);
      setSessionId(record.session_id);
      setTurns(
        record.messages
          .filter((message) => message.role === "user" || message.role === "assistant")
          .map((message) => ({
            role: message.role === "assistant" ? "assistant" : "user",
            content: message.content,
            citations: message.role === "assistant" ? record.citations : undefined,
          })),
      );
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIsSending(false);
    }
  }

  async function removeSession(nextSessionId: string) {
    if (isSending) return;
    try {
      await deleteChatSession(context.activeVaultSelector, nextSessionId);
      if (sessionId === nextSessionId) newSession();
      await refreshSessions();
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }

  async function archiveCurrentSession() {
    if (!sessionId || isSending || isArchiving) return;
    setIsArchiving(true);
    try {
      const response = await ingestChatSession(context.activeVaultSelector, sessionId);
      context.setNotice({
        message: response.run_id ? `${context.t("chatIngestQueued")} ${response.run_id}` : context.t("chatIngestQueued"),
      });
      await refreshSessions();
      context.navigate("runs");
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIsArchiving(false);
    }
  }

  async function closeCurrentSession() {
    if (!sessionId || isSending || isArchiving) return;
    setIsArchiving(true);
    try {
      const response = await closeChatSession(context.activeVaultSelector, sessionId);
      context.setNotice({
        message: response.ingest_started && response.run_id
          ? `${context.t("chatClosedAndIngestQueued")} ${response.run_id}`
          : context.t("chatClosed"),
      });
      await refreshSessions();
      if (response.ingest_started) context.navigate("runs");
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIsArchiving(false);
    }
  }

  async function submit(nextInput = input) {
    const content = nextInput.trim();
    if (!content || isSending) return;
    setInput("");
    const userTurn: ChatTurn = { role: "user", content };
    const nextTurns = [...turns, userTurn];
    setTurns(nextTurns);
    setIsSending(true);
    try {
      const response = await sendChatMessage(
        context.activeVaultSelector,
        [...apiMessages, { role: "user", content }],
        {
          session_id: sessionId,
          all_vaults: context.activeVaultId === "all",
          max_turns: 6,
        },
      );
      setSessionId(response.session_id || sessionId);
      setTurns((current) => [
        ...current,
        {
          role: "assistant",
          content: response.answer,
          citations: response.citations || [],
        },
      ]);
      void refreshSessions();
    } catch (error) {
      const rawMessage = error instanceof Error ? error.message : String(error);
      const message = readableChatError(rawMessage, context);
      context.setNotice({ message, error: true });
      setTurns((current) => [...current, { role: "assistant", content: message }]);
    } finally {
      setIsSending(false);
    }
  }

  const hasConversation = turns.length > 0 || isSending;

  return (
    <section className="view active chat-page">
      <div className="chat-layout">
        <aside className="panel chat-session-sidebar">
          <div className="chat-session-sidebar-header">
            <strong>{context.t("chatSessions")}</strong>
            <button className="icon-button" type="button" onClick={newSession} disabled={isSending} title={context.t("chatNewSession")}>
              +
            </button>
          </div>
          <div className="chat-session-list" aria-busy={isLoadingSessions}>
            {isLoadingSessions && <span className="chat-session-muted">{context.t("loading")}</span>}
            {!isLoadingSessions && recentSessions.length === 0 && <span className="chat-session-muted">{context.t("chatNoSessions")}</span>}
            {recentSessions.map((session) => (
              <div className={`chat-session-row ${session.session_id === sessionId ? "active" : ""}`} key={session.session_id}>
                <button type="button" onClick={() => void restoreSession(session.session_id)} disabled={isSending} title={session.title}>
                  {session.title}
                </button>
                <button
                  className="chat-session-delete"
                  type="button"
                  onClick={() => void removeSession(session.session_id)}
                  disabled={isSending}
                  title={context.t("chatDeleteSession")}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </aside>
        <article className="panel chat-thread-panel">
          <div className="chat-thread">
            {!hasConversation && (
              <div className="chat-empty-state">
                <span className="chat-eyebrow">{context.t("chatIntroEyebrow")}</span>
                <h2>{context.t("chatIntroTitle")}</h2>
                <p>{context.t("chatIntroCopy")}</p>
                <div className="chat-suggestion-grid" aria-label={context.t("chatSuggested")}>
                  {exampleKeys.map((key) => {
                    const example = context.t(key);
                    return (
                      <button key={key} type="button" onClick={() => void submit(example)} disabled={isSending}>
                        <span>{context.t("chatSuggested")}</span>
                        <strong>{example}</strong>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {turns.map((turn, index) => (
              <div className={`chat-message ${turn.role}`} key={`${turn.role}-${index}`}>
                <div className="chat-bubble">
                  {turn.role === "assistant" ? (
                    <ChatMarkdownAnswer content={turn.content} citations={turn.citations || []} context={context} />
                  ) : (
                    <p>{turn.content}</p>
                  )}
                  {!!turn.citations?.length && <CitationList citations={turn.citations} context={context} />}
                </div>
              </div>
            ))}
            {isSending && (
              <div className="chat-message assistant">
                <div className="chat-bubble">
                  <p className="muted-text">{context.t("chatThinking")}</p>
                </div>
              </div>
            )}
          </div>
          <div className="chat-composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              placeholder={context.t("chatPlaceholder")}
              rows={3}
            />
            <div className="chat-composer-actions">
              <div className="chat-session-actions">
                <button className="button ghost" type="button" onClick={() => void archiveCurrentSession()} disabled={!sessionId || isSending || isArchiving}>
                  {isArchiving ? context.t("chatArchiving") : context.t("chatIngestSession")}
                </button>
                <button className="button ghost" type="button" onClick={() => void closeCurrentSession()} disabled={!sessionId || isSending || isArchiving}>
                  {context.t("chatCloseSession")}
                </button>
              </div>
              <button className="button primary" type="button" onClick={() => void submit()} disabled={isSending || !input.trim()}>
                {isSending ? context.t("chatSending") : context.t("chatSend")}
              </button>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}

function ChatMarkdownAnswer({ content, citations, context }: { content: string; citations: ChatCitation[]; context: AppContext }) {
  return (
    <div className="chat-answer-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => {
            const href = props.href || "";
            if (href.startsWith("#knoarbor-citation=")) {
              const citationIndex = Number(decodeURIComponent(href.slice("#knoarbor-citation=".length)));
              const citation = citations[citationIndex];
              return (
                <button
                  className="chat-inline-citation"
                  type="button"
                  disabled={!citation}
                  onClick={() => citation && openCitation(citation, context)}
                >
                  {props.children}
                </button>
              );
            }
            return <a {...props} target="_blank" rel="noreferrer" />;
          },
        }}
      >
        {renderInlineCitations(content, citations.length)}
      </ReactMarkdown>
    </div>
  );
}

function renderInlineCitations(content: string, citationCount: number) {
  if (!citationCount) return content;
  return content.replace(/\[(\d+)\]/g, (match, rawIndex: string) => {
    const citationIndex = Number(rawIndex) - 1;
    if (!Number.isInteger(citationIndex) || citationIndex < 0 || citationIndex >= citationCount) return match;
    return `[[${rawIndex}]](#knoarbor-citation=${citationIndex})`;
  });
}

function CitationList({ citations, context, compact = false }: { citations: ChatCitation[]; context: AppContext; compact?: boolean }) {
  const groups = groupCitations(citations, context);
  return (
    <details className={`chat-citations ${compact ? "compact" : ""}`}>
      <summary>
        <span>{context.t("chatSources")}</span>
        <strong>{citations.length}</strong>
      </summary>
      <div className="chat-citation-list">
        {groups.map((group) => (
          <div className="chat-citation-group" key={group.label}>
            <span className="chat-citation-group-label">{group.label}</span>
            {group.items.map(({ citation, index }) => (
              <button
                key={`${citation.kind}-${citation.path || citation.run_id}-${index}`}
                type="button"
                onClick={() => openCitation(citation, context)}
                className="chat-citation-card"
              >
                <span className="chat-citation-index">{index + 1}</span>
                <span className="chat-citation-main">
                  <strong>{citation.title || citation.path || citation.run_id || citation.kind}</strong>
                  <small>{citation.vault_name || citation.vault_id || citation.kind}</small>
                </span>
                {citation.path && <code>{citation.path}</code>}
              </button>
            ))}
          </div>
        ))}
      </div>
    </details>
  );
}

function groupCitations(citations: ChatCitation[], context: AppContext) {
  const indexed = citations.map((citation, index) => ({ citation, index }));
  const specs = [
    { role: "primary", label: context.t("chatEvidencePrimary") },
    { role: "supporting", label: context.t("chatEvidenceSupporting") },
    { role: "source", label: context.t("chatEvidenceSource") },
  ];
  const groups = specs
    .map((spec) => ({
      label: spec.label,
      items: indexed.filter(({ citation }) => citation.role === spec.role || (!citation.role && spec.role === "supporting")),
    }))
    .filter((group) => group.items.length);
  const groupedIndexes = new Set(groups.flatMap((group) => group.items.map((item) => item.index)));
  const other = indexed.filter((item) => !groupedIndexes.has(item.index));
  if (other.length) groups.push({ label: context.t("chatEvidenceOther"), items: other });
  return groups;
}

function openCitation(citation: ChatCitation, context: AppContext) {
  if (citation.kind === "page" && citation.path) {
    context.openWikiPageInVault(citation.vault_id, citation.path);
    return;
  }
  if (citation.kind === "report" && citation.path) {
    context.openReport(citation.path);
    return;
  }
  if (citation.kind === "run") {
    context.navigate("runs");
  }
}

function readableChatError(message: string, context: AppContext): string {
  const lower = message.toLowerCase();
  if (lower.includes("invalid decision") || lower.includes("invalid json") || lower.includes("model_output")) {
    return context.t("chatErrorInvalidOutput");
  }
  if (
    lower.includes("model provider")
    || lower.includes("external_service")
    || lower.includes("provider endpoint")
    || lower.includes("api key")
    || lower.includes("connection")
    || lower.includes("timeout")
  ) {
    return context.t("chatErrorModelUnavailable");
  }
  if (lower.includes("vault") || lower.includes("knowledge base")) {
    return context.t("chatErrorVaultUnavailable");
  }
  return context.t("chatErrorService");
}
