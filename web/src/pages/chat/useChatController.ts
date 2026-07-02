import { useEffect, useMemo, useState } from "react";

import {
  deleteChatTurn,
  type ChatMessageItem,
} from "../../api/client";
import type { AppContext } from "../../appContext";
import {
  selectedProviderName,
  type ChatTurn,
} from "./ChatModel";
import { useChatSessionLifecycle } from "./useChatSessionLifecycle";
import { useChatSelectionIngest } from "./useChatSelectionIngest";
import { useChatStreaming } from "./useChatStreaming";
import { useCitationPreview } from "./useCitationPreview";
import { useSidebarChatSessions } from "./useSidebarChatSessions";

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
  const [contextMenu, setContextMenu] = useState<ChatContextMenuState | null>(null);
  const { refreshSidebarSessions } = useSidebarChatSessions();
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
  const {
    citationPreview,
    openCitationPreview,
    setCitationPreview,
  } = useCitationPreview(context);
  const selectionIngest = useChatSelectionIngest({
    chatVaultReady,
    context,
    sessionId,
    setContextMenu,
  });
  const sessionLifecycle = useChatSessionLifecycle({
    chatVaultReady,
    context,
    isSending,
    setInput,
    setIsSending,
    setSelectedMessageIndices: selectionIngest.setSelectedMessageIndices,
    setSessionId,
    setTurns,
  });
  const streaming = useChatStreaming({
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
  });

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

  function closeContextMenu() {
    setContextMenu(null);
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
      refreshSidebarSessions();
    } catch (error) {
      setTurns(previousTurns);
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }

  return {
    activeChatProvider,
    archiveExcerpt: selectionIngest.archiveExcerpt,
    chatModelProviders,
    citationPreview,
    clearMessageSelection: selectionIngest.clearMessageSelection,
    closeContextMenu,
    contextMenu,
    deleteTurn,
    ingestSelectedMessages: selectionIngest.ingestSelectedMessages,
    ingestingExcerptKey: selectionIngest.ingestingExcerptKey,
    ingestingMessages: selectionIngest.ingestingMessages,
    input,
    isRegenerating: streaming.isRegenerating,
    isSending,
    newSession: sessionLifecycle.newSession,
    openCitationPreview,
    regenerateLatestAnswer: streaming.regenerateLatestAnswer,
    regenerateTurn: streaming.regenerateTurn,
    requestStage: streaming.requestStage,
    selectedMessageIndices: selectionIngest.selectedMessageIndices,
    setCitationPreview,
    setContextMenu,
    setInput,
    sessionId,
    stopSending: streaming.stopSending,
    submit: streaming.submit,
    toggleMessageSelection: selectionIngest.toggleMessageSelection,
    turns,
  };
}
