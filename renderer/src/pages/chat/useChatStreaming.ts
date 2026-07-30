import { useEffect, useRef, useState } from "react";

import {
  retryChatSession,
  sendChatMessageStream,
  type ChatMessageItem,
  type ChatStreamEvent,
  type VaultSelector,
} from "../../api/client";
import type { ChatAppContext } from "../../appContext";
import { chatErrorPresentation, readableChatError } from "./ChatEvidence";
import {
  appendStreamingAssistantDelta,
  chatStageFromStreamEvent,
  latestAssistantTurnIndex,
  rawEvidenceFromChatResponse,
  replaceStreamingAssistant,
  type ChatRequestStage,
  type ChatTurn,
} from "./ChatModel";

type ChatStreamingInput = {
  activeChatProvider: string;
  apiMessages: ChatMessageItem[];
  chatVaultReady: boolean;
  chatVaultSelector: VaultSelector;
  context: ChatAppContext;
  input: string;
  isSending: boolean;
  refreshSidebarSessions: () => void;
  sessionId: string | null;
  sessionRevision: number | null;
  setInput: (value: string) => void;
  setIsSending: (value: boolean) => void;
  setSessionId: (value: string | null) => void;
  setSessionRevision: (value: number | null) => void;
  setTurns: (updater: ChatTurn[] | ((current: ChatTurn[]) => ChatTurn[])) => void;
  turns: ChatTurn[];
};

export function useChatStreaming({
  activeChatProvider,
  apiMessages,
  chatVaultReady,
  chatVaultSelector,
  context,
  input,
  isSending,
  refreshSidebarSessions,
  sessionId,
  sessionRevision,
  setInput,
  setIsSending,
  setSessionId,
  setSessionRevision,
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
        chatVaultSelector,
        [...apiMessages, { role: "user", content }],
        {
          session_id: sessionId,
          expected_session_revision: sessionId ? sessionRevision : null,
          all_vaults: context.chatScopeVaultId === "all",
          provider: activeChatProvider || undefined,
        },
        (event) => applyStreamEvent(event),
        controller.signal,
      );
      setSessionId(response.session_id || sessionId);
      setSessionRevision(response.session_revision);
      setTurns((current) => replaceStreamingAssistant(current, {
        role: "assistant",
        turnId: response.turn_id,
        content: response.answer,
        citations: response.citations || [],
        rawEvidence: rawEvidenceFromChatResponse(response),
        hiddenEvidenceCount: response.hidden_evidence_count || 0,
        citationWarnings: response.citation_warnings || [],
        answerProvenance: response.answer_provenance,
      }));
      refreshSidebarSessions();
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setTurns((current) => replaceStreamingAssistant(current, { role: "assistant", content: context.t("chatStoppedInline"), kind: "status" }));
        return;
      }
      const presentation = chatErrorPresentation(error, context);
      setTurns((current) => replaceStreamingAssistant(current, {
        role: "assistant",
        content: presentation.message,
        kind: "error",
        errorAction: presentation.action,
      }));
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
    const targetTurnId = turns[latestAssistantIndex]?.turnId;
    if (!targetTurnId || sessionRevision === null) return;
    const previousTurns = turns;
    setTurns(turns.slice(0, latestAssistantIndex));
    setIsRegenerating(true);
    setIsSending(true);
    beginRequestStages("regenerating");
    const controller = new AbortController();
    activeChatAbortRef.current = controller;
    try {
      const response = await retryChatSession(
        chatVaultSelector,
        sessionId,
        {
          all_vaults: context.chatScopeVaultId === "all",
          target_turn_id: targetTurnId,
          expected_session_revision: sessionRevision,
          provider: activeChatProvider || undefined,
        },
        controller.signal,
      );
      setSessionId(response.session_id || sessionId);
      setSessionRevision(response.session_revision);
      setTurns((current) => [
        ...current,
        {
          role: "assistant",
          turnId: response.turn_id,
          content: response.answer,
          citations: response.citations || [],
          rawEvidence: rawEvidenceFromChatResponse(response),
          hiddenEvidenceCount: response.hidden_evidence_count || 0,
          citationWarnings: response.citation_warnings || [],
          answerProvenance: response.answer_provenance,
        },
      ]);
      refreshSidebarSessions();
    } catch (error) {
      setTurns(previousTurns);
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      console.error("Chat regeneration failed", readableChatError(error, context));
    } finally {
      if (activeChatAbortRef.current === controller) activeChatAbortRef.current = null;
      clearStageTimers();
      setRequestStage("idle");
      setIsSending(false);
      setIsRegenerating(false);
    }
  }

  async function regenerateTurn(assistantIndex: number) {
    if (!sessionId || isSending || isRegenerating || !chatVaultReady || assistantIndex !== turns.length - 1) return;
    const userIndex = assistantIndex - 1;
    if (userIndex < 0 || turns[userIndex]?.role !== "user") return;
    const targetTurnId = turns[assistantIndex]?.turnId;
    if (!targetTurnId || sessionRevision === null) return;
    const truncatedTurns = turns.slice(0, userIndex + 1);
    const previousTurns = turns;
    setTurns([...truncatedTurns, { role: "assistant", content: "", streaming: true }]);
    setIsRegenerating(true);
    setIsSending(true);
    beginRequestStages("regenerating");
    const controller = new AbortController();
    activeChatAbortRef.current = controller;
    try {
      const response = await retryChatSession(
        chatVaultSelector,
        sessionId,
        {
          target_turn_id: targetTurnId,
          expected_session_revision: sessionRevision,
          all_vaults: context.chatScopeVaultId === "all",
          provider: activeChatProvider || undefined,
        },
        controller.signal,
      );
      setTurns((current) => replaceStreamingAssistant(current, {
        role: "assistant",
        turnId: response.turn_id,
        content: response.answer,
        citations: response.citations || [],
        rawEvidence: rawEvidenceFromChatResponse(response),
        hiddenEvidenceCount: response.hidden_evidence_count || 0,
        citationWarnings: response.citation_warnings || [],
        answerProvenance: response.answer_provenance,
      }));
      setSessionRevision(response.session_revision);
      refreshSidebarSessions();
    } catch (error) {
      setTurns(previousTurns);
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      console.error("Chat turn regeneration failed", readableChatError(error, context));
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
