import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
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

type ChatFollowup = {
  kind: "question" | "page";
  label: string;
  prompt?: string;
  citation?: ChatCitation;
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
  const activeChatAbortRef = useRef<AbortController | null>(null);
  const chatVaultReady = useMemo(() => {
    const selector = context.activeVaultSelector;
    if (!context.configExists || !context.vaultOptions.length) return false;
    if (selector.vault_id) {
      return context.vaultOptions.some((vault) => vault.id === selector.vault_id);
    }
    return Boolean(selector.vault_path);
  }, [context.activeVaultSelector, context.configExists, context.vaultOptions]);

  const apiMessages = useMemo<ChatMessageItem[]>(
    () => turns
      .filter((turn) => turn.role === "user" || turn.role === "assistant")
      .slice(-10)
      .map((turn) => ({ role: turn.role, content: turn.content })),
    [turns],
  );

  useEffect(() => {
    if (!chatVaultReady) return;
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
  }, [chatVaultReady, context.activeVaultSelector]);

  useEffect(() => {
    const prompt = context.pendingChatPrompt.trim();
    if (!prompt) return;
    setInput(prompt);
    context.clearPendingChatPrompt();
  }, [context.pendingChatPrompt, context.clearPendingChatPrompt]);

  async function refreshSessions() {
    if (!chatVaultReady) return;
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
    if (isSending || !chatVaultReady) return;
    setIsSending(true);
    try {
      const record = await readChatSession(context.activeVaultSelector, nextSessionId);
      setSessionId(record.session_id);
      setTurns(sessionRecordToTurns(record));
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIsSending(false);
    }
  }

  async function removeSession(nextSessionId: string) {
    if (isSending || !chatVaultReady) return;
    try {
      await deleteChatSession(context.activeVaultSelector, nextSessionId);
      if (sessionId === nextSessionId) newSession();
      await refreshSessions();
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }

  async function archiveSession(nextSessionId: string) {
    if (!nextSessionId || isSending || isArchiving || !chatVaultReady) return;
    setIsArchiving(true);
    try {
      const response = await ingestChatSession(context.activeVaultSelector, nextSessionId);
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

  async function submit(nextInput = input) {
    const content = nextInput.trim();
    if (!content || isSending || !chatVaultReady) return;
    setInput("");
    const userTurn: ChatTurn = { role: "user", content };
    const nextTurns = [...turns, userTurn];
    setTurns(nextTurns);
    setIsSending(true);
    const controller = new AbortController();
    activeChatAbortRef.current = controller;
    try {
      const response = await sendChatMessage(
        context.activeVaultSelector,
        [...apiMessages, { role: "user", content }],
        {
          session_id: sessionId,
          all_vaults: context.activeVaultId === "all",
          max_turns: 6,
        },
        controller.signal,
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
      if (error instanceof DOMException && error.name === "AbortError") {
        context.setNotice({ message: context.t("chatStopped") });
        return;
      }
      const rawMessage = error instanceof Error ? error.message : String(error);
      const message = readableChatError(rawMessage, context);
      context.setNotice({ message, error: true });
      setTurns((current) => [...current, { role: "assistant", content: message }]);
    } finally {
      if (activeChatAbortRef.current === controller) {
        activeChatAbortRef.current = null;
      }
      setIsSending(false);
    }
  }

  function stopSending() {
    activeChatAbortRef.current?.abort();
  }

  const hasConversation = turns.length > 0 || isSending;

  return (
    <section className="view active chat-page">
      <div className="chat-layout">
        <aside className="chat-session-sidebar">
          <div className="chat-session-sidebar-header">
            <span>
              <strong>{context.t("chatSessions")}</strong>
              <small>{recentSessions.length ? `${recentSessions.length} ${context.t("chatSessions").toLowerCase()}` : context.t("chatNoSessions")}</small>
            </span>
            <button className="icon-button chat-new-button" type="button" onClick={newSession} disabled={isSending} title={context.t("chatNewSession")} aria-label={context.t("chatNewSession")}>
              +
            </button>
          </div>
          <div className="chat-session-list" aria-busy={isLoadingSessions}>
            {isLoadingSessions && <span className="chat-session-muted">{context.t("loading")}</span>}
            {!isLoadingSessions && recentSessions.length === 0 && <span className="chat-session-muted">{context.t("chatNoSessions")}</span>}
            {recentSessions.map((session) => (
              <div className={`chat-session-row ${session.session_id === sessionId ? "active" : ""}`} key={session.session_id}>
                <button type="button" onClick={() => void restoreSession(session.session_id)} disabled={isSending} title={session.title}>
                  <span className="chat-session-title">{session.title}</span>
                  <span className="chat-session-preview">{session.last_message || formatSessionDate(session.updated_at)}</span>
                </button>
                <details className="chat-session-menu">
                  <summary aria-label={context.t("chatSessionActions")} title={context.t("chatSessionActions")}>⋯</summary>
                  <div className="chat-session-menu-popover">
                    <button
                      type="button"
                      onClick={() => void archiveSession(session.session_id)}
                      disabled={isSending || isArchiving}
                    >
                      {isArchiving ? context.t("chatArchiving") : context.t("chatIngestSession")}
                    </button>
                    <button
                      className="danger"
                      type="button"
                      onClick={() => void removeSession(session.session_id)}
                      disabled={isSending || isArchiving}
                    >
                      {context.t("chatDeleteSession")}
                    </button>
                  </div>
                </details>
              </div>
            ))}
          </div>
        </aside>
        <article className="chat-thread-panel">
          <div className="chat-thread">
            {!hasConversation && (
              <div className="chat-empty-state">
                <div className="chat-empty-header">
                  <span className="chat-eyebrow">{context.t("chatIntroEyebrow")}</span>
                  <h2>{context.t("chatIntroTitle")}</h2>
                  <p>{context.t("chatIntroCopy")}</p>
                </div>
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
                  {turn.role === "assistant" && !!turn.citations?.length && (
                    <ChatFollowups
                      citations={turn.citations}
                      context={context}
                      disabled={isSending}
                      onAsk={(prompt) => void submit(prompt)}
                    />
                  )}
                </div>
              </div>
            ))}
            {isSending && (
              <div className="chat-message assistant">
                <div className="chat-bubble">
                  <div className="chat-thinking">
                    <span />
                    <span />
                    <span />
                    <p>{context.t("chatThinking")}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="chat-composer">
            <div className="chat-input-shell">
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
                rows={2}
              />
              <button
                className={`button ${isSending ? "secondary" : "primary"} chat-send-button`}
                type="button"
                onClick={isSending ? stopSending : () => void submit()}
                disabled={!isSending && !input.trim()}
                title={isSending ? context.t("chatStop") : context.t("chatSend")}
              >
                {isSending ? context.t("chatStop") : context.t("chatSend")}
              </button>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}

function sessionRecordToTurns(record: Awaited<ReturnType<typeof readChatSession>>): ChatTurn[] {
  if (record.turns?.length) {
    return record.turns.flatMap((turn) => [
      { role: "user" as const, content: turn.user_message.content },
      {
        role: "assistant" as const,
        content: turn.assistant_message.content,
        citations: turn.citations || [],
      },
    ]);
  }
  return record.messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content,
      citations: message.role === "assistant" ? record.citations : undefined,
    }));
}

function formatSessionDate(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
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

function ChatFollowups({ citations, context, disabled, onAsk }: { citations: ChatCitation[]; context: AppContext; disabled: boolean; onAsk: (prompt: string) => void }) {
  const followups = buildChatFollowups(citations, context);
  if (!followups.length) return null;
  const questions = followups.filter((item) => item.kind === "question");
  const pages = followups.filter((item) => item.kind === "page");
  return (
    <div className="chat-followups">
      <span className="chat-followups-title">{context.t("chatFollowups")}</span>
      {!!questions.length && (
        <div className="chat-followup-row" aria-label={context.t("chatFollowupQuestions")}>
          {questions.map((item) => (
            <button key={item.label} type="button" disabled={disabled} onClick={() => item.prompt && onAsk(item.prompt)}>
              <span>{context.t("chatAskFollowup")}</span>
              <strong>{item.label}</strong>
            </button>
          ))}
        </div>
      )}
      {!!pages.length && (
        <div className="chat-followup-row pages" aria-label={context.t("chatFollowupPages")}>
          {pages.map((item) => (
            <button key={item.label} type="button" onClick={() => item.citation && openCitation(item.citation, context)}>
              <span>{context.t("chatOpenPage")}</span>
              <strong>{item.label}</strong>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function buildChatFollowups(citations: ChatCitation[], context: AppContext): ChatFollowup[] {
  const pages = uniquePageCitations(citations).filter((citation) => citation.kind === "page" && citation.path);
  if (!pages.length) return [];
  const answerPages = pages.filter((citation) => citation.role !== "source" && !citation.path?.startsWith("sources/"));
  const primary = answerPages.find((citation) => citation.role === "primary") || answerPages[0] || pages[0];
  const supporting = answerPages.filter((citation) => citation.path !== primary.path).slice(0, 2);
  const questions = uniqueFollowups([
    questionForPage(primary, context, "primary"),
    supporting[0] ? relationQuestion(primary, supporting[0], context) : undefined,
    supporting[1] ? relationQuestion(primary, supporting[1], context) : undefined,
  ]).slice(0, 3);
  const pageSuggestions = [...answerPages, ...pages.filter((citation) => citation.role === "source")]
    .slice(0, 3)
    .map((citation) => ({
      kind: "page" as const,
      label: citationTitle(citation),
      citation,
    }));
  return [...questions, ...pageSuggestions];
}

function uniquePageCitations(citations: ChatCitation[]) {
  const seen = new Set<string>();
  const unique: ChatCitation[] = [];
  for (const citation of citations) {
    const key = `${citation.kind}:${citation.vault_id || ""}:${citation.path || citation.run_id || citation.title || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(citation);
  }
  return unique;
}

function uniqueFollowups(items: Array<ChatFollowup | undefined>) {
  const seen = new Set<string>();
  const unique: ChatFollowup[] = [];
  for (const item of items) {
    if (!item || seen.has(item.label)) continue;
    seen.add(item.label);
    unique.push(item);
  }
  return unique;
}

function questionForPage(citation: ChatCitation, context: AppContext, role: "primary" | "supporting"): ChatFollowup {
  const title = citationTitle(citation);
  const isZh = context.language === "zh";
  const looksLikeComparison = /vs|versus|compare|comparison|对比|区别/i.test(title);
  let prompt: string;
  if (looksLikeComparison) {
    prompt = isZh ? `详细总结 ${title} 的主要差异和适用场景` : `Summarize the key differences and use cases in ${title}`;
  } else if (role === "primary") {
    prompt = isZh ? `进一步解释 ${title} 的关键机制和实践要点` : `Explain the key mechanisms and practical takeaways of ${title}`;
  } else {
    prompt = isZh ? `展开讲讲 ${title} 和当前问题的关系` : `Explain how ${title} relates to the current question`;
  }
  return { kind: "question", label: prompt, prompt };
}

function relationQuestion(primary: ChatCitation, supporting: ChatCitation, context: AppContext): ChatFollowup {
  const primaryTitle = citationTitle(primary);
  const supportingTitle = citationTitle(supporting);
  const prompt = context.language === "zh"
    ? `${primaryTitle} 和 ${supportingTitle} 有什么关系？`
    : `How are ${primaryTitle} and ${supportingTitle} related?`;
  return { kind: "question", label: prompt, prompt };
}

function citationTitle(citation: ChatCitation) {
  if (citation.title?.trim()) return citation.title.trim();
  if (citation.path?.trim()) {
    const name = citation.path.split("/").pop() || citation.path;
    return name.replace(/\.md$/i, "").replace(/-/g, " ");
  }
  return citation.run_id || citation.kind;
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
