import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  deleteChatTurn,
  getPage,
  ingestChatSession,
  ingestExcerpt,
  readChatSession,
  retryChatSession,
  sendChatMessageStream,
  type ChatCitation,
  type ChatMessageItem,
  type ChatStreamEvent,
  type PageDetail,
  type ModelProviderSummary,
  type VaultSelector,
} from "../api/client";
import type { AppContext } from "../App";
import { pathBaseName } from "../pathUtils";

type Props = {
  context: AppContext;
};

type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
  hiddenEvidenceCount?: number;
  citationWarnings?: string[];
  kind?: "answer" | "error" | "status";
  streaming?: boolean;
};

type ChatFollowup = {
  kind: "question" | "page";
  label: string;
  prompt?: string;
  citation?: ChatCitation;
};

type ChatRequestStage = "idle" | "preparing" | "retrieving" | "generating" | "waiting_model" | "regenerating";

type ChatCitationPreview = {
  citation: ChatCitation;
  page: PageDetail | null;
  loading: boolean;
  error: string | null;
};

const exampleKeys = ["chatExampleAgentLoop", "chatExampleLint", "chatExampleRag", "chatExampleReadPage"];

export function ChatPage({ context }: Props) {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [ingestingExcerptKey, setIngestingExcerptKey] = useState<string | null>(null);
  const [selectedMessageIndices, setSelectedMessageIndices] = useState<Set<number>>(new Set());
  const selectionActive = selectedMessageIndices.size > 0;
  const [ingestingMessages, setIngestingMessages] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; messageIndex: number } | null>(null);
  const [requestStage, setRequestStage] = useState<ChatRequestStage>("idle");
  const [citationPreview, setCitationPreview] = useState<ChatCitationPreview | null>(null);
  const activeChatAbortRef = useRef<AbortController | null>(null);
  const stageTimersRef = useRef<number[]>([]);
  const chatModelProviders = useMemo(() => context.modelProviders?.providers || [], [context.modelProviders]);
  const activeChatProvider = useMemo(
    () => selectedProviderName(context.selectedChatProvider, context.modelProviders?.default_provider, chatModelProviders),
    [chatModelProviders, context.modelProviders?.default_provider, context.selectedChatProvider],
  );
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
    const prompt = context.pendingChatPrompt.trim();
    if (!prompt) return;
    setInput(prompt);
    context.clearPendingChatPrompt();
  }, [context.pendingChatPrompt, context.clearPendingChatPrompt]);

  useEffect(() => {
    const request = context.pendingChatSessionRequest;
    if (!request || isSending || !chatVaultReady) return;
    context.clearPendingChatSessionRequest();
    if (request.sessionId) {
      void restoreSession(request.sessionId);
      return;
    }
    newSession();
  }, [chatVaultReady, context.pendingChatSessionRequest, context.clearPendingChatSessionRequest, isSending]);

  useEffect(() => () => clearStageTimers(), []);

  function newSession() {
    if (isSending) return;
    setSessionId(null);
    setTurns([]);
    setInput("");
    setSelectedMessageIndices(new Set());
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

  async function archiveExcerpt(turn: ChatTurn, index: number) {
    if (turn.role !== "assistant" || turn.kind === "error" || turn.kind === "status" || !chatVaultReady) return;
    const excerptText = selectedTextOrTurnContent(turn.content);
    if (!excerptText) {
      context.setNotice({ message: context.t("chatExcerptEmpty"), error: true });
      return;
    }
    const excerptKey = `${index}:${excerptText.slice(0, 24)}`;
    setIngestingExcerptKey(excerptKey);
    try {
      const response = await ingestExcerpt(context.activeVaultSelector, {
        excerpt_text: excerptText,
        excerpt_title: buildExcerptTitle(excerptText),
        excerpt_context: {
          source_app: "knoarbor_chat",
          session_id: sessionId,
          turn_index: index,
          role: turn.role,
          selection_used: selectedTextOrNull() !== null,
        },
      });
      context.setNotice({
        message: response.run_id ? `${context.t("chatExcerptQueued")} ${response.run_id}` : context.t("chatExcerptQueued"),
        actionLabel: context.t("viewRun"),
        onAction: () => context.navigate("runs"),
      });
      await context.refreshAll();
      context.navigate("runs");
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIngestingExcerptKey(null);
    }
  }

  function toggleMessageSelection(messageIndex: number) {
    setSelectedMessageIndices((prev) => {
      const next = new Set(prev);
      if (next.has(messageIndex)) next.delete(messageIndex);
      else next.add(messageIndex);
      return next;
    });
  }

  function clearMessageSelection() {
    setSelectedMessageIndices(new Set());
  }

  async function ingestSelectedMessages() {
    if (!sessionId || !selectedMessageIndices.size || !chatVaultReady) return;
    const indices = Array.from(selectedMessageIndices).sort((a, b) => a - b);
    const turnIndices = [...new Set(indices.map((i) => Math.floor(i / 2)))];
    setIngestingMessages(true);
    setContextMenu(null);
    try {
      const response = await ingestChatSession(context.activeVaultSelector, sessionId, { turn_indices: turnIndices });
      context.setNotice({
        message: response.run_id ? `${context.t("chatExcerptQueued")} ${response.run_id}` : context.t("chatExcerptQueued"),
        actionLabel: context.t("viewRun"),
        onAction: () => context.navigate("runs"),
      });
      await context.refreshAll();
      context.navigate("runs");
      setSelectedMessageIndices(new Set());
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIngestingMessages(false);
    }
  }

  function closeContextMenu() {
    setContextMenu(null);
  }

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    document.addEventListener("click", close);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    return () => {
      document.removeEventListener("click", close);
    };
  }, [contextMenu]);

  async function submit(nextInput = input) {
    const content = nextInput.trim();
    if (!content || isSending || !chatVaultReady) return;
    setInput("");
    const userTurn: ChatTurn = { role: "user", content };
    const assistantPlaceholder: ChatTurn = { role: "assistant", content: "", streaming: true };
    const nextTurns = [...turns, userTurn, assistantPlaceholder];
    setTurns(nextTurns);
    setIsSending(true);
    beginRequestStages("preparing");
    const controller = new AbortController();
    activeChatAbortRef.current = controller;
    try {
      const response = await sendChatMessageStream(
        context.activeVaultSelector,
        [...apiMessages, { role: "user", content }],
        {
          session_id: sessionId,
          all_vaults: context.activeVaultId === "all",
          max_turns: 6,
          provider: activeChatProvider || undefined,
        },
        (event) => applyStreamEvent(event),
        controller.signal,
      );
      setSessionId(response.session_id || sessionId);
      setTurns((current) => replaceStreamingAssistant(current, {
          role: "assistant",
          content: response.answer,
          citations: response.citations || [],
          hiddenEvidenceCount: response.hidden_evidence_count || 0,
          citationWarnings: response.citation_warnings || [],
        }));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        context.setNotice({ message: context.t("chatStopped") });
        setTurns((current) => replaceStreamingAssistant(current, { role: "assistant", content: context.t("chatStoppedInline"), kind: "status" }));
        return;
      }
      const rawMessage = error instanceof Error ? error.message : String(error);
      const message = readableChatError(rawMessage, context);
      context.setNotice({ message, error: true });
      setTurns((current) => replaceStreamingAssistant(current, { role: "assistant", content: message, kind: "error" }));
    } finally {
      if (activeChatAbortRef.current === controller) {
        activeChatAbortRef.current = null;
      }
      clearStageTimers();
      setRequestStage("idle");
      setIsSending(false);
    }
  }

  function stopSending() {
    activeChatAbortRef.current?.abort();
  }

  async function openCitationPreview(citation: ChatCitation) {
    if (citation.kind !== "page" || !citation.path) {
      openCitationTarget(citation, context);
      return;
    }
    setCitationPreview({ citation, page: null, loading: true, error: null });
    try {
      const page = await getPage(citationSelector(citation, context), citation.path);
      setCitationPreview({ citation, page, loading: false, error: null });
    } catch (error) {
      setCitationPreview({
        citation,
        page: null,
        loading: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async function regenerateLatestAnswer() {
    if (!sessionId || isSending || isRegenerating || !chatVaultReady) return;
    const latestAssistantIndex = latestAssistantTurnIndex(turns);
    if (latestAssistantIndex < 0) return;
    const previousTurns = turns;
    const nextTurns = turns.slice(0, latestAssistantIndex);
    setTurns(nextTurns);
    setIsRegenerating(true);
    setIsSending(true);
    beginRequestStages("regenerating");
    const controller = new AbortController();
    activeChatAbortRef.current = controller;
    try {
      const response = await retryChatSession(
        context.activeVaultSelector,
        sessionId,
        {
          all_vaults: context.activeVaultId === "all",
          max_turns: 6,
          provider: activeChatProvider || undefined,
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
          hiddenEvidenceCount: response.hidden_evidence_count || 0,
          citationWarnings: response.citation_warnings || [],
        },
      ]);
    } catch (error) {
      setTurns(previousTurns);
      if (error instanceof DOMException && error.name === "AbortError") {
        context.setNotice({ message: context.t("chatStopped") });
        return;
      }
      const rawMessage = error instanceof Error ? error.message : String(error);
      context.setNotice({ message: readableChatError(rawMessage, context), error: true });
    } finally {
      if (activeChatAbortRef.current === controller) {
        activeChatAbortRef.current = null;
      }
      clearStageTimers();
      setRequestStage("idle");
      setIsSending(false);
      setIsRegenerating(false);
    }
  }

  async function deleteTurn(assistantIndex: number) {
    if (isSending || assistantIndex < 1) return;
    const userIndex = assistantIndex - 1;
    if (turns[userIndex]?.role !== "user" || turns[assistantIndex]?.role !== "assistant") return;
    const turnIndex = Math.floor(assistantIndex / 2);
    const previousTurns = turns;
    setTurns(turns.filter((_, i) => i !== userIndex && i !== assistantIndex));
    if (sessionId) {
      try {
        await deleteChatTurn(context.activeVaultSelector, sessionId, turnIndex);
      } catch (error) {
        setTurns(previousTurns);
        context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      }
    }
  }

  async function regenerateTurn(assistantIndex: number) {
    if (!sessionId || isSending || isRegenerating || !chatVaultReady) return;
    const userIndex = assistantIndex - 1;
    if (userIndex < 0 || turns[userIndex]?.role !== "user") return;
    const userTurn = turns[userIndex];
    const truncatedTurns = turns.slice(0, userIndex + 1);
    const assistantPlaceholder: ChatTurn = { role: "assistant", content: "", streaming: true };
    const nextTurns = [...truncatedTurns, assistantPlaceholder];
    const previousTurns = turns;
    setTurns(nextTurns);
    setIsRegenerating(true);
    setIsSending(true);
    beginRequestStages("regenerating");
    const truncatedMessages: ChatMessageItem[] = truncatedTurns
      .filter((t) => t.role === "user" || t.role === "assistant")
      .map((t) => ({ role: t.role, content: t.content }));
    const controller = new AbortController();
    activeChatAbortRef.current = controller;
    try {
      const response = await sendChatMessageStream(
        context.activeVaultSelector,
        truncatedMessages,
        {
          session_id: sessionId,
          all_vaults: context.activeVaultId === "all",
          max_turns: 6,
          provider: activeChatProvider || undefined,
        },
        (event) => applyStreamEvent(event),
        controller.signal,
      );
      setTurns((current) => replaceStreamingAssistant(current, {
        role: "assistant",
        content: response.answer,
        citations: response.citations || [],
        hiddenEvidenceCount: response.hidden_evidence_count || 0,
        citationWarnings: response.citation_warnings || [],
      }));
    } catch (error) {
      setTurns(previousTurns);
      if (error instanceof DOMException && error.name === "AbortError") {
        context.setNotice({ message: context.t("chatStopped") });
        return;
      }
      const rawMessage = error instanceof Error ? error.message : String(error);
      context.setNotice({ message: readableChatError(rawMessage, context), error: true });
    } finally {
      if (activeChatAbortRef.current === controller) {
        activeChatAbortRef.current = null;
      }
      clearStageTimers();
      setRequestStage("idle");
      setIsSending(false);
      setIsRegenerating(false);
    }
  }

  function beginRequestStages(initialStage: ChatRequestStage) {
    clearStageTimers();
    setRequestStage(initialStage);
    if (initialStage === "regenerating") {
      stageTimersRef.current = [
        window.setTimeout(() => setRequestStage("retrieving"), 650),
        window.setTimeout(() => setRequestStage("generating"), 1800),
        window.setTimeout(() => setRequestStage("waiting_model"), 5200),
      ];
      return;
    }
    stageTimersRef.current = [
      window.setTimeout(() => setRequestStage("retrieving"), 450),
      window.setTimeout(() => setRequestStage("generating"), 1600),
      window.setTimeout(() => setRequestStage("waiting_model"), 5000),
    ];
  }

  function applyStreamEvent(event: ChatStreamEvent) {
    if (event.event === "answer_delta") {
      const delta = typeof event.payload?.delta === "string" ? event.payload.delta : "";
      if (delta) {
        setTurns((current) => appendStreamingAssistantDelta(current, delta));
      }
    }
    const nextStage = chatStageFromStreamEvent(event);
    if (nextStage) {
      clearStageTimers();
      setRequestStage(nextStage);
    }
  }

  function clearStageTimers() {
    for (const timer of stageTimersRef.current) window.clearTimeout(timer);
    stageTimersRef.current = [];
  }

  const hasConversation = turns.length > 0 || isSending;
  return (
    <section className="view active chat-page">
      <div className="chat-layout">
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
            {turns.map((turn, index) => {
              const isSelected = selectedMessageIndices.has(index);
              return (
              <div
                className={`chat-message ${turn.role}${isSelected ? " selected-for-ingest" : ""}`}
                key={`${turn.role}-${index}`}
                onContextMenu={(e) => {
                  e.preventDefault();
                  if (isSending) return;
                  setContextMenu({ x: e.clientX, y: e.clientY, messageIndex: index });
                }}
              >
                {selectionActive && (
                  <label className="chat-select-checkbox">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleMessageSelection(index)}
                      disabled={isSending || ingestingMessages}
                    />
                  </label>
                )}
                <div className="chat-bubble">
                  {turn.kind === "error" ? (
                    <ChatErrorMessage message={turn.content} context={context} />
                  ) : turn.kind === "status" ? (
                    <ChatStatusMessage message={turn.content} />
                  ) : turn.role === "assistant" ? (
                    <ChatMarkdownAnswer content={turn.content} citations={turn.citations || []} context={context} onOpenCitation={(citation) => void openCitationPreview(citation)} />
                  ) : (
                    <p>{turn.content}</p>
                  )}
                  {turn.role === "assistant" && turn.kind !== "error" && turn.kind !== "status" && (
                    <div className="chat-message-actions">
                      <button type="button" onClick={() => deleteTurn(index)} disabled={isSending}>
                        {context.language === "zh" ? "删除此轮" : "Delete turn"}
                      </button>
                      <button type="button" onClick={() => regenerateTurn(index)} disabled={isSending || isRegenerating}>
                        {context.language === "zh" ? "重新生成" : "Regenerate"}
                      </button>
                    </div>
                  )}
                  {(!!turn.citations?.length || !!turn.hiddenEvidenceCount) && (
                    <CitationList
                      citations={turn.citations || []}
                      hiddenEvidenceCount={turn.hiddenEvidenceCount || 0}
                      context={context}
                      onOpenCitation={(citation) => void openCitationPreview(citation)}
                    />
                  )}
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
            );
            })}
            {isSending && (
              <div className="chat-message assistant">
                <div className="chat-bubble">
                  <div className="chat-thinking" aria-live="polite">
                    <span />
                    <span />
                    <span />
                    <p>{chatStageLabel(requestStage, context)}</p>
                  </div>
                </div>
              </div>
            )}
            {selectedMessageIndices.size > 0 && (
              <div className="chat-ingest-floatbar">
                <span>{context.language === "zh"
                  ? `已选 ${selectedMessageIndices.size} 条消息`
                  : `${selectedMessageIndices.size} message(s) selected`}</span>
                <button className="button compact" type="button" onClick={clearMessageSelection}>
                  {context.language === "zh" ? "清除" : "Clear"}
                </button>
                <button
                  className="button primary compact"
                  type="button"
                  onClick={() => void ingestSelectedMessages()}
                  disabled={ingestingMessages}
                >
                  {ingestingMessages
                    ? (context.language === "zh" ? "摄入中..." : "Ingesting...")
                    : context.t("chatIngestExcerpt")}
                </button>
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
              <div className="chat-input-footer">
                <div className="chat-input-left-tools">
                  {!!context.vaultOptions.length && (
                    <div className="chat-vault-toolbar" title={context.t("activeVault")}>
                      <select
                        value={context.activeVaultId}
                        onChange={(event) => context.setActiveVaultId(event.target.value)}
                        disabled={isSending}
                        aria-label={context.t("activeVault")}
                      >
                        {context.vaultOptions.map((vault) => (
                          <option value={vault.id} key={vault.id}>
                            {vault.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
                {!!chatModelProviders.length ? (
                  <div
                    className="chat-model-toolbar"
                    title={chatProviderStatusLabel(activeChatProvider, context)}
                  >
                    <select
                      value={activeChatProvider}
                      onChange={(event) => context.setSelectedChatProvider(event.target.value)}
                      disabled={isSending}
                      aria-label={context.t("model")}
                    >
                      {chatModelProviders.map((provider) => (
                        <option value={provider.name} key={provider.name}>
                          {modelProviderOptionLabel(provider)}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <span />
                )}
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
          </div>
        </article>
        {contextMenu && (
          <ChatContextMenu
            contextMenu={contextMenu}
            context={context}
            turns={turns}
            sessionId={sessionId}
            selectedMessageIndices={selectedMessageIndices}
            isSending={isSending}
            ingestingMessages={ingestingMessages}
            ingestingExcerptKey={ingestingExcerptKey}
            onToggleMessage={toggleMessageSelection}
            onCompileExcerpt={archiveExcerpt}
            onIngestSelected={() => void ingestSelectedMessages()}
            onClose={closeContextMenu}
          />
        )}
        {citationPreview && (
          <ChatCitationPreviewPanel
            context={context}
            preview={citationPreview}
            onClose={() => setCitationPreview(null)}
            onAsk={(prompt) => {
              setCitationPreview(null);
              void submit(prompt);
            }}
          />
        )}
      </div>
    </section>
  );
}

function selectedTextOrNull(): string | null {
  if (typeof window === "undefined") return null;
  const selected = window.getSelection()?.toString().trim();
  return selected || null;
}

function selectedTextOrTurnContent(content: string): string {
  return selectedTextOrNull() || content.trim();
}

function buildExcerptTitle(content: string): string {
  const compact = content
    .replace(/\s+/g, " ")
    .replace(/^#+\s*/, "")
    .trim();
  if (!compact) return "Chat excerpt";
  return compact.length > 48 ? `${compact.slice(0, 48)}...` : compact;
}

function appendStreamingAssistantDelta(turns: ChatTurn[], delta: string): ChatTurn[] {
  const lastIndex = turns.length - 1;
  const last = turns[lastIndex];
  if (!last || last.role !== "assistant" || !last.streaming) {
    return [...turns, { role: "assistant", content: delta, streaming: true }];
  }
  return [
    ...turns.slice(0, lastIndex),
    { ...last, content: `${last.content}${delta}` },
  ];
}

function replaceStreamingAssistant(turns: ChatTurn[], replacement: ChatTurn): ChatTurn[] {
  const lastIndex = turns.length - 1;
  const last = turns[lastIndex];
  if (!last || last.role !== "assistant" || !last.streaming) {
    return [...turns, replacement];
  }
  return [...turns.slice(0, lastIndex), replacement];
}

function ChatStatusMessage({ message }: { message: string }) {
  return <div className="chat-status-card">{message}</div>;
}

function ChatContextMenu({
  contextMenu,
  context,
  turns,
  sessionId,
  selectedMessageIndices,
  isSending,
  ingestingMessages,
  ingestingExcerptKey,
  onToggleMessage,
  onCompileExcerpt,
  onIngestSelected,
  onClose,
}: {
  contextMenu: { x: number; y: number; messageIndex: number };
  context: AppContext;
  turns: ChatTurn[];
  sessionId: string | null;
  selectedMessageIndices: Set<number>;
  isSending: boolean;
  ingestingMessages: boolean;
  ingestingExcerptKey: string | null;
  onToggleMessage: (index: number) => void;
  onCompileExcerpt: (turn: ChatTurn, index: number) => void;
  onIngestSelected: () => void;
  onClose: () => void;
}) {
  const { messageIndex } = contextMenu;
  const turn = turns[messageIndex];
  const isSelected = selectedMessageIndices.has(messageIndex);
  const hasTextSelection = (typeof window !== "undefined" && window.getSelection()?.toString().trim()) || false;
  const isExcerptable = turn?.role === "assistant" && turn.kind !== "error" && turn.kind !== "status" && sessionId;
  const zh = context.language === "zh";
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuPos, setMenuPos] = useState<{ left: number; top: number }>({ left: contextMenu.x, top: contextMenu.y });

  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    const rect = menu.getBoundingClientRect();
    let left = contextMenu.x;
    let top = contextMenu.y;
    if (left + rect.width > window.innerWidth - 8) left = window.innerWidth - rect.width - 8;
    if (top + rect.height > window.innerHeight - 8) top = window.innerHeight - rect.height - 8;
    if (left < 4) left = 4;
    if (top < 4) top = 4;
    setMenuPos({ left, top });
  }, [contextMenu.x, contextMenu.y]);

  return (
    <div ref={menuRef} className="chat-context-menu" style={{ left: menuPos.left, top: menuPos.top }}>
      <button type="button" onClick={() => { onToggleMessage(messageIndex); onClose(); }}>
        {isSelected ? (zh ? "取消选择此消息" : "Deselect this message") : (zh ? "选择此消息" : "Select this message")}
      </button>
      {isExcerptable && hasTextSelection && (
        <button
          type="button"
          disabled={isSending || ingestingExcerptKey !== null}
          onClick={() => { onCompileExcerpt(turn, messageIndex); onClose(); }}
        >
          {ingestingExcerptKey?.startsWith(`${messageIndex}:`) ? (zh ? "编译中..." : "Compiling...") : (zh ? "编译摘录" : "Compile excerpt")}
        </button>
      )}
      {selectedMessageIndices.size > 0 && (
        <>
          <hr />
          <button
            type="button"
            disabled={ingestingMessages}
            onClick={() => { onIngestSelected(); }}
          >
            {ingestingMessages
              ? (zh ? "摄入中..." : "Ingesting...")
              : (zh ? `摄入选中 (${selectedMessageIndices.size})` : `Ingest selected (${selectedMessageIndices.size})`)}
          </button>
        </>
      )}
    </div>
  );
}

function ChatErrorMessage({ message, context }: { message: string; context: AppContext }) {
  return (
    <div className="chat-error-card" role="alert">
      <strong>{context.t("chatErrorTitle")}</strong>
      <p>{message}</p>
      <div className="chat-error-actions">
        <button type="button" onClick={context.openSettings}>{context.t("openSettings")}</button>
      </div>
    </div>
  );
}

function chatStageLabel(stage: ChatRequestStage, context: AppContext) {
  if (stage === "regenerating") return context.t("chatStageRegenerating");
  if (stage === "retrieving") return context.t("chatStageRetrieving");
  if (stage === "generating") return context.t("chatStageGenerating");
  if (stage === "waiting_model") return context.t("chatStageWaitingModel");
  return context.t("chatStagePreparing");
}

function chatStageFromStreamEvent(event: ChatStreamEvent): ChatRequestStage | null {
  if (event.event === "final") return "generating";
  if (event.event === "error") return "idle";
  if (event.stage === "planning" || event.stage === "preparing") return "preparing";
  if (event.stage === "retrieving") return "retrieving";
  if (event.stage === "generating") return "waiting_model";
  if (event.stage === "completed") return "generating";
  if (event.tool) return "retrieving";
  return null;
}

function selectedProviderName(selected: string, defaultProvider: string | null | undefined, providers: ModelProviderSummary[]) {
  if (selected && providers.some((provider) => provider.name === selected)) return selected;
  if (defaultProvider && providers.some((provider) => provider.name === defaultProvider)) return defaultProvider;
  return providers[0]?.name || "";
}

function modelProviderOptionLabel(provider: ModelProviderSummary) {
  return provider.name;
}

function chatProviderStatus(providerName: string, providers: ModelProviderSummary[], context: AppContext) {
  const provider = providers.find((item) => item.name === providerName);
  if (!provider) return "unknown";
  const result = currentModelProbeResult(provider, context.modelProbeResults[provider.name]);
  if (!result) return provider.api_key_env && !provider.api_key_configured ? "error" : "unknown";
  if (result.status === "ok" && result.available) return "ok";
  if (result.status === "warning" || result.available) return "warning";
  return "error";
}

function chatProviderStatusLabel(providerName: string, context: AppContext) {
  const provider = context.modelProviders?.providers.find((item) => item.name === providerName);
  if (!provider) return context.t("modelNotChecked");
  const result = currentModelProbeResult(provider, context.modelProbeResults[provider.name]);
  if (!result) {
    if (provider.api_key_env && !provider.api_key_configured) return context.t("envMissing");
    return context.t("modelNotChecked");
  }
  if (result.status === "ok" && result.available) return context.t("modelAvailable");
  if (result.status === "warning" || result.available) return context.t("modelNeedsAttention");
  return context.t("modelUnavailable");
}

function currentModelProbeResult(provider: ModelProviderSummary, result: AppContext["modelProbeResults"][string]) {
  if (!result) return undefined;
  if (result.probe?.model === provider.model) return result.probe;
  const discoveryModels = result.discovery?.model_ids || [];
  if (result.discovery && (!provider.model || discoveryModels.includes(provider.model))) return result.discovery;
  return undefined;
}

function sessionRecordToTurns(record: Awaited<ReturnType<typeof readChatSession>>): ChatTurn[] {
  if (record.turns?.length) {
    return record.turns.flatMap((turn) => [
      { role: "user" as const, content: turn.user_message.content },
      {
        role: "assistant" as const,
        content: turn.assistant_message.content,
        citations: turn.citations || [],
        hiddenEvidenceCount: turn.hidden_evidence_count || 0,
        citationWarnings: turn.citation_warnings || [],
      },
    ]);
  }
  return record.messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content,
      citations: message.role === "assistant" ? record.citations : undefined,
      hiddenEvidenceCount: message.role === "assistant" ? record.hidden_evidence_count || 0 : undefined,
      citationWarnings: message.role === "assistant" ? record.citation_warnings || [] : undefined,
    }));
}

function latestAssistantTurnIndex(turns: ChatTurn[]) {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (turns[index].role === "assistant" && turns[index].kind !== "error" && turns[index].kind !== "status") return index;
  }
  return -1;
}

function formatSessionDate(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ChatMarkdownAnswer({
  content,
  citations,
  context,
  onOpenCitation,
}: {
  content: string;
  citations: ChatCitation[];
  context: AppContext;
  onOpenCitation: (citation: ChatCitation) => void;
}) {
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
                  onClick={() => citation && onOpenCitation(citation)}
                >
                  {props.children}
                </button>
              );
            }
            return <a {...props} target="_blank" rel="noreferrer" />;
          },
          img: (props) => {
            const resolvedSrc = resolveChatImageSrc(props.src, citations, context);
            return <img {...props} src={resolvedSrc} alt={props.alt || ""} loading="lazy" />;
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

function CitationList({
  citations,
  hiddenEvidenceCount = 0,
  context,
  compact = false,
  onOpenCitation,
}: {
  citations: ChatCitation[];
  hiddenEvidenceCount?: number;
  context: AppContext;
  compact?: boolean;
  onOpenCitation: (citation: ChatCitation) => void;
}) {
  const groups = groupCitations(citations, context);
  return (
    <details className={`chat-citations ${compact ? "compact" : ""}`}>
      <summary>
        <span>{context.t("chatSourcesCompact")}</span>
        <strong>{citations.length}</strong>
      </summary>
      {hiddenEvidenceCount > 0 && (
        <p className="chat-hidden-evidence">{context.t("chatHiddenEvidence").replace("{count}", String(hiddenEvidenceCount))}</p>
      )}
      <div className="chat-citation-list">
        {groups.map((group) => (
          <div className="chat-citation-group" key={group.label}>
            <span className="chat-citation-group-label">{group.label}</span>
            {group.items.map(({ citation, index }) => (
              <button
                key={`${citation.kind}-${citation.path || citation.run_id}-${index}`}
                type="button"
                onClick={() => onOpenCitation(citation)}
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

function ChatFollowups({
  citations,
  context,
  disabled,
  onAsk,
}: {
  citations: ChatCitation[];
  context: AppContext;
  disabled: boolean;
  onAsk: (prompt: string) => void;
}) {
  const followups = buildChatFollowups(citations, context);
  if (!followups.length) return null;
  const questions = followups.filter((item) => item.kind === "question");
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
    </div>
  );
}

function ChatCitationPreviewPanel({
  context,
  preview,
  onAsk,
  onClose,
}: {
  context: AppContext;
  preview: ChatCitationPreview;
  onAsk: (prompt: string) => void;
  onClose: () => void;
}) {
  const title = preview.page?.summary.title || citationTitle(preview.citation);
  const path = preview.citation.path || preview.page?.path || "";
  return (
    <aside className="chat-preview-panel" aria-label={context.t("chatSourcePreview")}>
      <div className="chat-preview-header">
        <div>
          <span className="eyebrow">{context.t("chatSourcePreview")}</span>
          <h3>{title}</h3>
          {path && <code>{path}</code>}
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label={context.t("close")}>×</button>
      </div>
      {preview.loading && (
        <div className="chat-preview-state">
          <strong>{context.t("wikiPageLoading")}</strong>
          <p>{context.t("wikiPageLoadingCopy")}</p>
        </div>
      )}
      {!preview.loading && preview.error && (
        <div className="chat-error-card">
          <strong>{context.t("chatSourcePreviewFailed")}</strong>
          <p>{preview.error}</p>
          <div className="chat-error-actions">
            <button type="button" onClick={() => openCitationTarget(preview.citation, context)}>
              {context.t("viewInKnowledgeBase")}
            </button>
          </div>
        </div>
      )}
      {!preview.loading && preview.page && (
        <>
          <div className="chat-preview-summary">
            <p>{preview.page.summary.summary || context.t("noSummary")}</p>
          </div>
          <div className="chat-preview-actions">
            <button
              className="button secondary"
              type="button"
              onClick={() => onAsk(followupPromptForCitation(preview.citation, context))}
            >
              {context.t("chatAskAboutThisPage")}
            </button>
            <button
              className="button secondary"
              type="button"
              onClick={() => openCitationTarget(preview.citation, context)}
            >
              {context.t("viewInKnowledgeBase")}
            </button>
          </div>
          <div className="chat-preview-content">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                img: (props) => {
                  const resolvedSrc = resolveVaultAssetImageSrc(props.src, preview.citation.vault_path || context.activeVaultSelector.vault_path || context.vaultPath);
                  return <img {...props} src={resolvedSrc} alt={props.alt || ""} loading="lazy" />;
                },
              }}
            >
              {preview.page.content}
            </ReactMarkdown>
          </div>
        </>
      )}
    </aside>
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
  return questions;
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
    const name = pathBaseName(citation.path);
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

function citationSelector(citation: ChatCitation, context: AppContext): VaultSelector {
  return {
    config_path: context.activeVaultSelector.config_path,
    vault_id: citation.vault_id || context.activeVaultSelector.vault_id,
    vault_path: citation.vault_id ? undefined : citation.vault_path || context.activeVaultSelector.vault_path,
  };
}

function followupPromptForCitation(citation: ChatCitation, context: AppContext) {
  const title = citationTitle(citation);
  return context.language === "zh"
    ? `围绕 ${title} 继续展开，结合这页内容讲清楚关键机制和实践要点`
    : `Continue with ${title}; explain the key mechanisms and practical takeaways from this page.`;
}

function openCitationTarget(citation: ChatCitation, context: AppContext) {
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

function resolveChatImageSrc(src: string | undefined, citations: ChatCitation[], context: AppContext): string | undefined {
  const citationVaultPath = citations.find((citation) => citation.vault_path)?.vault_path;
  return resolveVaultAssetImageSrc(src, citationVaultPath || context.activeVaultSelector.vault_path || context.vaultPath);
}

function resolveVaultAssetImageSrc(src: string | undefined, vaultPath: string | undefined): string | undefined {
  if (!src || /^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("//") || src.startsWith("/")) return src;
  const assetPath = vaultAssetPathFromSrc(src);
  if (!assetPath || !vaultPath) return src;
  return `/ui/api/vault-assets/${encodeURIComponent(assetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
}

function vaultAssetPathFromSrc(src: string): string | null {
  let cleaned = src.replace(/\\/g, "/").replace(/^\.\//, "");
  if (cleaned.startsWith("../assets/")) cleaned = cleaned.slice("../assets/".length);
  else if (cleaned.startsWith("raw/assets/")) cleaned = cleaned.slice("raw/assets/".length);
  else if (cleaned.startsWith("assets/")) cleaned = cleaned.slice("assets/".length);
  if (/^(images|media|pages|tables)\//.test(cleaned)) return cleaned;
  return null;
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
