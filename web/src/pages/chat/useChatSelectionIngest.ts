import { useState } from "react";

import { ingestChatSession, ingestExcerpt } from "../../api/client";
import type { AppContext } from "../../appContext";
import {
  buildExcerptTitle,
  selectedTextOrNull,
  selectedTextOrTurnContent,
  type ChatTurn,
} from "./ChatModel";

type ChatSelectionIngestInput = {
  chatVaultReady: boolean;
  context: AppContext;
  sessionId: string | null;
  setContextMenu: (value: null) => void;
};

export function useChatSelectionIngest({ chatVaultReady, context, sessionId, setContextMenu }: ChatSelectionIngestInput) {
  const [ingestingExcerptKey, setIngestingExcerptKey] = useState<string | null>(null);
  const [selectedMessageIndices, setSelectedMessageIndices] = useState<Set<number>>(new Set());
  const [ingestingMessages, setIngestingMessages] = useState(false);

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

  return {
    archiveExcerpt,
    clearMessageSelection,
    ingestSelectedMessages,
    ingestingExcerptKey,
    ingestingMessages,
    selectedMessageIndices,
    setSelectedMessageIndices,
    toggleMessageSelection,
  };
}
