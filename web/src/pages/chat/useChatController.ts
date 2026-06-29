import { useEffect, useMemo, useRef, useState } from "react";

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
} from "../../api/client";
import type { AppContext } from "../../appContext";
import { citationSelector, openCitationTarget, readableChatError } from "./ChatEvidence";
import {
  appendStreamingAssistantDelta,
  buildExcerptTitle,
  chatStageFromStreamEvent,
  latestAssistantTurnIndex,
  replaceStreamingAssistant,
  selectedProviderName,
  selectedTextOrNull,
  selectedTextOrTurnContent,
  sessionRecordToTurns,
  type ChatCitationPreview,
  type ChatRequestStage,
  type ChatTurn,
} from "./ChatModel";

export type ChatContextMenuState = {
  x: number;
  y: number;
  messageIndex: number;
};

export function useChatController(context: AppContext) {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [ingestingExcerptKey, setIngestingExcerptKey] = useState<string | null>(null);
  const [selectedMessageIndices, setSelectedMessageIndices] = useState<Set<number>>(new Set());
  const [ingestingMessages, setIngestingMessages] = useState(false);
  const [contextMenu, setContextMenu] = useState<ChatContextMenuState | null>(null);
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
    if (selector.vault_id) return context.vaultOptions.some((vault) => vault.id === selector.vault_id);
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

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [contextMenu]);

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
    const turnIndices = [...new Set(indices.map((index) => Math.floor(index / 2)))];
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

  async function submit(nextInput = input) {
    const content = nextInput.trim();
    if (!content || isSending || !chatVaultReady) return;
    setInput("");
    setTurns((current) => [...current, { role: "user", content }, { role: "assistant", content: "", streaming: true }]);
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
      if (activeChatAbortRef.current === controller) activeChatAbortRef.current = null;
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
    setTurns(turns.slice(0, latestAssistantIndex));
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
      if (activeChatAbortRef.current === controller) activeChatAbortRef.current = null;
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
    setTurns(turns.filter((_, index) => index !== userIndex && index !== assistantIndex));
    if (!sessionId) return;
    try {
      await deleteChatTurn(context.activeVaultSelector, sessionId, turnIndex);
    } catch (error) {
      setTurns(previousTurns);
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }

  async function regenerateTurn(assistantIndex: number) {
    if (!sessionId || isSending || isRegenerating || !chatVaultReady) return;
    const userIndex = assistantIndex - 1;
    if (userIndex < 0 || turns[userIndex]?.role !== "user") return;
    const truncatedTurns = turns.slice(0, userIndex + 1);
    const previousTurns = turns;
    setTurns([...truncatedTurns, { role: "assistant", content: "", streaming: true }]);
    setIsRegenerating(true);
    setIsSending(true);
    beginRequestStages("regenerating");
    const truncatedMessages: ChatMessageItem[] = truncatedTurns
      .filter((turn) => turn.role === "user" || turn.role === "assistant")
      .map((turn) => ({ role: turn.role, content: turn.content }));
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
      if (activeChatAbortRef.current === controller) activeChatAbortRef.current = null;
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
      if (delta) setTurns((current) => appendStreamingAssistantDelta(current, delta));
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

  return {
    activeChatProvider,
    archiveExcerpt,
    chatModelProviders,
    citationPreview,
    clearMessageSelection,
    closeContextMenu,
    contextMenu,
    deleteTurn,
    ingestSelectedMessages,
    ingestingExcerptKey,
    ingestingMessages,
    input,
    isRegenerating,
    isSending,
    newSession,
    openCitationPreview,
    regenerateLatestAnswer,
    regenerateTurn,
    requestStage,
    selectedMessageIndices,
    setCitationPreview,
    setContextMenu,
    setInput,
    sessionId,
    stopSending,
    submit,
    toggleMessageSelection,
    turns,
  };
}
