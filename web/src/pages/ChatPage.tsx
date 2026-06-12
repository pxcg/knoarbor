import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
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
  const [mode, setMode] = useState<"quick" | "balanced" | "deep">("balanced");
  const [scope, setScope] = useState<"current" | "all">("current");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [recentSessions, setRecentSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const apiMessages = useMemo<ChatMessageItem[]>(
    () => turns
      .filter((turn) => turn.role === "user" || turn.role === "assistant")
      .slice(-10)
      .map((turn) => ({ role: turn.role, content: turn.content })),
    [turns],
  );

  useEffect(() => {
    let cancelled = false;
    if (turns.length > 0) return;
    setIsLoadingSessions(true);
    listChatSessions(context.activeVaultSelector, 6)
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
  }, [context.activeVaultSelector, turns.length]);

  async function restoreSession(nextSessionId: string) {
    if (isSending) return;
    setIsSending(true);
    try {
      const record = await readChatSession(context.activeVaultSelector, nextSessionId);
      setSessionId(record.session_id);
      setTurns(record.messages.map((message) => ({ role: message.role === "assistant" ? "assistant" : "user", content: message.content })));
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIsSending(false);
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
          mode,
          all_vaults: scope === "all" || context.activeVaultId === "all",
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
                {(isLoadingSessions || recentSessions.length > 0) && (
                  <div className="chat-recent-sessions">
                    <div className="chat-recent-heading">
                      <strong>{context.language === "zh" ? "最近会话" : "Recent chats"}</strong>
                      {isLoadingSessions && <span>{context.t("loading")}</span>}
                    </div>
                    <div className="chat-recent-list">
                      {recentSessions.map((session) => (
                        <button key={session.session_id} type="button" onClick={() => void restoreSession(session.session_id)} disabled={isSending}>
                          <strong>{session.title}</strong>
                          <span>{session.last_message || session.updated_at}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            {turns.map((turn, index) => (
              <div className={`chat-message ${turn.role}`} key={`${turn.role}-${index}`}>
                <div className="chat-avatar">{turn.role === "user" ? context.t("chatUser") : "K"}</div>
                <div className="chat-bubble">
                  <div className="chat-role">{turn.role === "user" ? context.t("chatUser") : context.t("chatAssistant")}</div>
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
                <div className="chat-avatar">K</div>
                <div className="chat-bubble">
                  <div className="chat-role">{context.t("chatAssistant")}</div>
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
              <details className="chat-advanced">
                <summary>{context.t("chatAdvanced")}</summary>
                <div className="chat-advanced-grid">
                  <label className="field compact-field">
                    <span>{context.t("chatMode")}</span>
                    <select value={mode} onChange={(event) => setMode(event.target.value as "quick" | "balanced" | "deep")}>
                      <option value="quick">{context.t("quickQuery")}</option>
                      <option value="balanced">{context.t("balancedQuery")}</option>
                      <option value="deep">{context.t("deepQuery")}</option>
                    </select>
                  </label>
                  <label className="field compact-field">
                    <span>{context.t("chatScope")}</span>
                    <select value={scope} onChange={(event) => setScope(event.target.value as "current" | "all")}>
                      <option value="current">{context.t("queryCurrentVault")}</option>
                      <option value="all">{context.t("queryAllVaults")}</option>
                    </select>
                  </label>
                </div>
              </details>
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
  return (
    <details className={`chat-citations ${compact ? "compact" : ""}`}>
      <summary>
        <span>{context.t("chatSources")}</span>
        <strong>{citations.length}</strong>
      </summary>
      <div className="chat-citation-list">
        {citations.map((citation, index) => (
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
    </details>
  );
}

function openCitation(citation: ChatCitation, context: AppContext) {
  if (citation.kind === "page" && citation.path) {
    context.openWikiPage(citation.path);
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
  if (lower.includes("model provider") || lower.includes("model") || lower.includes("external_service")) {
    return context.t("chatErrorModelUnavailable");
  }
  if (lower.includes("invalid decision") || lower.includes("invalid json") || lower.includes("model_output")) {
    return context.t("chatErrorInvalidOutput");
  }
  if (lower.includes("vault") || lower.includes("knowledge base")) {
    return context.t("chatErrorVaultUnavailable");
  }
  return context.t("chatErrorService");
}
