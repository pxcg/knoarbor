import { useEffect, useRef, useState } from "react";

import {
  retryChatSession,
  sendChatMessageStream,
  type ChatMessageItem,
  type ChatStreamEvent,
} from "../../api/client";
import type { AppContext } from "../../appContext";
import { readableChatError } from "./ChatEvidence";
import {
  appendStreamingAssistantDelta,
  chatStageFromStreamEvent,
  latestAssistantTurnIndex,
  replaceStreamingAssistant,
  type ChatRequestStage,
  type ChatTurn,
} from "./ChatModel";

type ChatStreamingInput = {
  activeChatProvider: string;
  apiMessages: ChatMessageItem[];
  chatVaultReady: boolean;
  context: AppContext;
  input: string;
  isSending: boolean;
  refreshSidebarSessions: () => void;
  sessionId: string | null;
  setInput: (value: string) => void;
  setIsSending: (value: boolean) => void;
  setSessionId: (value: string | null) => void;
  setTurns: (updater: ChatTurn[] | ((current: ChatTurn[]) => ChatTurn[])) => void;
  turns: ChatTurn[];
};

export function useChatStreaming({
  activeChatProvider,
  apiMessages,
  chatVaultReady,
  context,
  input,
  isSending,
  refreshSidebarSessions,
  sessionId,
  setInput,
  setIsSending,
  setSessionId,
  setTurns,
  turns,
}: ChatStreamingInput) {
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [requestStage, setRequestStage] = useState<ChatRequestStage>("idle");
  const activeChatAbortRef = useRef<AbortController | null>(null);
  const stageTimersRef = useRef<number[]>([]);

  useEffect(() => () => clearStageTimers(), []);

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
      refreshSidebarSessions();
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
      refreshSidebarSessions();
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
      refreshSidebarSessions();
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
    isRegenerating,
    regenerateLatestAnswer,
    regenerateTurn,
    requestStage,
    stopSending,
    submit,
  };
}
