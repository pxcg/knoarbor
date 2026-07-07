import { useEffect } from "react";

import { readChatSession } from "../../api/client";
import type { AppContext } from "../../appContext";
import { sessionRecordToTurns, type ChatTurn } from "./ChatModel";

type ChatSessionLifecycleInput = {
  chatVaultReady: boolean;
  context: AppContext;
  isSending: boolean;
  setInput: (value: string) => void;
  setIsSending: (value: boolean) => void;
  setSelectedMessageIndices: (value: Set<number>) => void;
  setSessionId: (value: string | null) => void;
  setTurns: (updater: ChatTurn[] | ((current: ChatTurn[]) => ChatTurn[])) => void;
};

export function useChatSessionLifecycle({
  chatVaultReady,
  context,
  isSending,
  setInput,
  setIsSending,
  setSelectedMessageIndices,
  setSessionId,
  setTurns,
}: ChatSessionLifecycleInput) {
  useEffect(() => {
    const prompt = context.pendingChatPrompt.trim();
    if (!prompt) return;
    setInput(prompt);
    context.clearPendingChatPrompt();
  }, [context.pendingChatPrompt, context.clearPendingChatPrompt, setInput]);

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

  return { newSession, restoreSession };
}
