import { useEffect, useMemo, useState } from "react";

import {
  deleteChatTurn,
  type ChatCitation,
  type ChatMessageItem,
  type VaultSelector,
} from "../../api/client";
import type { ChatAppContext } from "../../appContext";
import {
  evidenceForCitation,
  selectedProviderName,
  type ChatTurn,
} from "./ChatModel";
import { sameCitationDocument } from "./ChatEvidence";
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

export function useChatController(context: ChatAppContext) {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionRevision, setSessionRevision] = useState<number | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [contextMenu, setContextMenu] = useState<ChatContextMenuState | null>(null);
  const { refreshSidebarSessions } = useSidebarChatSessions();
  const chatModelProviders = useMemo(() => context.modelProviders?.providers || [], [context.modelProviders]);
  const activeChatProvider = useMemo(
    () => selectedProviderName(context.selectedChatProvider, context.modelProviders?.default_provider, chatModelProviders),
    [chatModelProviders, context.modelProviders?.default_provider, context.selectedChatProvider],
  );
  const chatVaultReady = useMemo(() => {
    if (!context.configExists || !context.vaultOptions.length) return false;
    if (context.chatScopeVaultId === "all") return context.vaultOptions.some((vault) => vault.id === "all");
    if (context.chatScopeVaultSelector.vault_id) return context.vaultOptions.some((vault) => vault.id === context.chatScopeVaultSelector.vault_id);
    return Boolean(context.chatScopeVaultSelector.vault_path);
  }, [context.chatScopeVaultId, context.chatScopeVaultSelector, context.configExists, context.vaultOptions]);
  const chatVaultSelector = useMemo<VaultSelector>(
    () => context.chatScopeVaultSelector,
    [context.chatScopeVaultSelector],
  );

  const apiMessages = useMemo<ChatMessageItem[]>(
    () => turns
      .filter((turn) => turn.role === "user" || turn.role === "assistant")
      .map((turn) => ({ role: turn.role, content: turn.content })),
    [turns],
  );
  const {
    citationPreview,
    clearCitationPreview,
    openCitationPreview,
  } = useCitationPreview(context);

  function showCitation(citation: ChatCitation, relatedCitations: ChatCitation[] = [citation]) {
    const evidenceItems = turns.flatMap((turn) => turn.rawEvidence || []);
    const evidence = evidenceForCitation(citation, evidenceItems);
    const related = relatedCitations
      .filter((item) => sameCitationDocument(citation, item))
      .map((item) => ({
        citation: item,
        evidence: evidenceForCitation(item, evidenceItems),
      }));
    return openCitationPreview(citation, evidence, related);
  }
  const selectionIngest = useChatSelectionIngest({
    chatVaultReady,
    context,
    sessionId,
    setContextMenu,
    turns,
  });
  const sessionLifecycle = useChatSessionLifecycle({
    chatVaultReady,
    chatVaultSelector,
    context,
    isSending,
    clearCitationPreview,
    setInput,
    setIsSending,
    setSelectedMessageIndices: selectionIngest.setSelectedMessageIndices,
    setSessionId,
    setSessionRevision,
    setTurns,
  });
  const streaming = useChatStreaming({
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
    if (isSending || assistantIndex < 1 || assistantIndex !== turns.length - 1) return;
    const userIndex = assistantIndex - 1;
    if (turns[userIndex]?.role !== "user" || turns[assistantIndex]?.role !== "assistant") return;
    const turnId = turns[assistantIndex]?.turnId;
    if (!turnId || sessionRevision === null) return;
    const previousTurns = turns;
    setTurns(turns.filter((_, index) => index !== userIndex && index !== assistantIndex));
    if (!sessionId) return;
    try {
      const record = await deleteChatTurn(chatVaultSelector, sessionId, turnId, sessionRevision);
      setSessionRevision(record.session_revision);
      refreshSidebarSessions();
    } catch (error) {
      setTurns(previousTurns);
      console.error("Chat turn deletion failed", error);
    }
  }

  return {
    activeChatProvider,
    archiveExcerpt: selectionIngest.archiveExcerpt,
    chatModelProviders,
    citationPreview,
    clearMessageSelection: selectionIngest.clearMessageSelection,
    cancelPendingIngest: selectionIngest.cancelPendingIngest,
    confirmPendingIngest: selectionIngest.confirmPendingIngest,
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
    openCitationPreview: showCitation,
    regenerateLatestAnswer: streaming.regenerateLatestAnswer,
    regenerateTurn: streaming.regenerateTurn,
    requestStage: streaming.requestStage,
    pendingIngest: selectionIngest.pendingIngest,
    selectedMessageIndices: selectionIngest.selectedMessageIndices,
    closeCitationPreview: clearCitationPreview,
    setContextMenu,
    setInput,
    updatePendingExcerpt: selectionIngest.updatePendingExcerpt,
    sessionId,
    stopSending: streaming.stopSending,
    submit: streaming.submit,
    toggleMessageSelection: selectionIngest.toggleMessageSelection,
    turns,
  };
}
