import { useEffect } from "react";

import { readChatSession, type VaultSelector } from "../../api/client";
import type { ChatAppContext } from "../../appContext";
import { sessionRecordToTurns, type ChatTurn } from "./ChatModel";

type ChatSessionLifecycleInput = {
  chatVaultReady: boolean;
  chatVaultSelector: VaultSelector;
  context: ChatAppContext;
  isSending: boolean;
  clearCitationPreview: () => void;
  setInput: (value: string) => void;
  setIsSending: (value: boolean) => void;
  setSelectedMessageIndices: (value: Set<number>) => void;
  setSessionId: (value: string | null) => void;
  setSessionRevision: (value: number | null) => void;
  setTurns: (updater: ChatTurn[] | ((current: ChatTurn[]) => ChatTurn[])) => void;
};

export function useChatSessionLifecycle({
  chatVaultReady,
  chatVaultSelector,
  context,
  isSending,
  clearCitationPreview,
  setInput,
  setIsSending,
  setSelectedMessageIndices,
  setSessionId,
  setSessionRevision,
  setTurns,
}: ChatSessionLifecycleInput) {
  useEffect(() => {
    const target = context.navigationTarget;
    if (target?.kind !== "chat-prompt" || isSending || !chatVaultReady) return;
    if (target.vaultId !== context.chatScopeVaultId) return;
    newSession();
    const prompt = target.prompt.trim();
    if (prompt) setInput(prompt);
    context.consumeNavigationTarget(target.requestId);
  }, [chatVaultReady, context.chatScopeVaultId, context.consumeNavigationTarget, context.navigationTarget, isSending, setInput]);

  useEffect(() => {
    const target = context.navigationTarget;
    if (target?.kind !== "chat-session" || isSending || !chatVaultReady) return;
    if (target.vaultId !== context.chatScopeVaultId) return;
    if (!target.sessionId) {
      newSession();
      context.consumeNavigationTarget(target.requestId);
      return;
    }
    let cancelled = false;
    clearCitationPreview();
    setIsSending(true);
    readChatSession(chatVaultSelector, target.sessionId)
      .then((record) => {
        if (cancelled) return;
        setSessionId(record.session_id);
        setSessionRevision(record.session_revision);
        setTurns(sessionRecordToTurns(record));
        context.consumeNavigationTarget(target.requestId);
      })
      .catch((error) => {
        if (cancelled) return;
        setSessionId(null);
        setSessionRevision(null);
        setInput("");
        setSelectedMessageIndices(new Set());
        setTurns([{
          role: "assistant",
          kind: "error",
          content: context.language === "zh" ? "该会话不存在或暂时无法读取。" : "The requested session does not exist or is temporarily unavailable.",
        }]);
        console.error("Chat session restore failed", error);
        context.consumeNavigationTarget(target.requestId);
      })
      .finally(() => {
        if (!cancelled) setIsSending(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    chatVaultReady,
    chatVaultSelector,
    clearCitationPreview,
    context.chatScopeVaultId,
    context.consumeNavigationTarget,
    context.language,
    context.navigationTarget,
    setInput,
    setIsSending,
    setSelectedMessageIndices,
    setSessionId,
    setSessionRevision,
    setTurns,
  ]);

  function newSession() {
    if (isSending) return;
    clearCitationPreview();
    setSessionId(null);
    setSessionRevision(null);
    setTurns([]);
    setInput("");
    setSelectedMessageIndices(new Set());
  }

  async function restoreSession(nextSessionId: string) {
    if (isSending || !chatVaultReady) return;
    clearCitationPreview();
    setIsSending(true);
    try {
      const record = await readChatSession(chatVaultSelector, nextSessionId);
      setSessionId(record.session_id);
      setSessionRevision(record.session_revision);
      setTurns(sessionRecordToTurns(record));
    } catch (error) {
      console.error("Chat session restore failed", error);
    } finally {
      setIsSending(false);
    }
  }

  return { newSession, restoreSession };
}
