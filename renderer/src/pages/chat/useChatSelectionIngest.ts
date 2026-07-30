import { useState } from "react";

import type { ChatAppContext } from "../../appContext";
import {
  defaultExcerptTargetVaultId,
  excerptDraftIsValid,
  submitExcerptDraft,
  type ExcerptIngestDraft,
} from "../../ingest/excerptIngest";
import {
  buildExcerptTitle,
  selectedTextOrNull,
  selectedTextOrTurnContent,
  type ChatTurn,
} from "./ChatModel";

type ChatSelectionIngestInput = {
  chatVaultReady: boolean;
  context: ChatAppContext;
  sessionId: string | null;
  setContextMenu: (value: null) => void;
  turns: ChatTurn[];
};

type PendingChatIngest = { kind: "excerpt"; key: string } & ExcerptIngestDraft;

export function useChatSelectionIngest({ chatVaultReady, context, sessionId, setContextMenu, turns }: ChatSelectionIngestInput) {
  const [ingestingExcerptKey, setIngestingExcerptKey] = useState<string | null>(null);
  const [selectedMessageIndices, setSelectedMessageIndices] = useState<Set<number>>(new Set());
  const [ingestingMessages, setIngestingMessages] = useState(false);
  const [pendingIngest, setPendingIngest] = useState<PendingChatIngest | null>(null);

  function archiveExcerpt(turn: ChatTurn, index: number) {
    if (turn.role !== "assistant" || !turnCanBeIngested(turn) || !chatVaultReady) return;
    const excerptText = selectedTextOrTurnContent(turn.content);
    if (!excerptText) {
      return;
    }
    const excerptKey = `${index}:${excerptText.slice(0, 24)}`;
    setPendingIngest({
      kind: "excerpt",
      content: excerptText,
      title: buildExcerptTitle(excerptText),
      targetVaultId: defaultExcerptTargetVaultId(context),
      key: excerptKey,
      context: {
          source_app: "knoarbor_chat",
          session_id: sessionId,
          turn_id: turn.turnId,
          message_id: turn.messageId,
          role: turn.role,
          selection_used: selectedTextOrNull() !== null,
      },
    });
  }

  function toggleMessageSelection(messageIndex: number) {
    if (!turnCanBeIngested(turns[messageIndex])) return;
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

  function ingestSelectedMessages() {
    if (!sessionId || !selectedMessageIndices.size || !chatVaultReady) return;
    const indices = Array.from(selectedMessageIndices).sort((a, b) => a - b);
    setPendingIngest({
      kind: "excerpt",
      content: selectedMessagesContent(turns, indices),
      context: {
        source_app: "knoarbor_chat",
        session_id: sessionId,
        message_indices: indices,
        selection_used: true,
      },
      key: `selected:${indices.join(",")}`,
      title: selectedMessagesTitle(turns, indices),
      targetVaultId: defaultExcerptTargetVaultId(context),
    });
  }

  function updatePendingExcerpt(draft: ExcerptIngestDraft) {
    setPendingIngest((current) => current ? { ...current, ...draft } : current);
  }

  function cancelPendingIngest() {
    if (ingestingMessages || ingestingExcerptKey) return;
    setPendingIngest(null);
  }

  async function confirmPendingIngest() {
    if (!excerptDraftIsValid(pendingIngest)) return;
    setIngestingMessages(true);
    setContextMenu(null);
    setIngestingExcerptKey(pendingIngest.key);
    try {
      const response = await submitExcerptDraft(context.configPath, pendingIngest);
      await context.refreshAll();
      if (response.run_id) context.openRun(response.run_id, pendingIngest.targetVaultId, response.flow);
      else context.navigate("ingest");
      setSelectedMessageIndices(new Set());
      setPendingIngest(null);
    } catch (error) {
      console.error("Chat excerpt ingest failed", error);
    } finally {
      setIngestingMessages(false);
      setIngestingExcerptKey(null);
    }
  }

  return {
    archiveExcerpt,
    clearMessageSelection,
    ingestSelectedMessages,
    ingestingExcerptKey,
    ingestingMessages,
    pendingIngest,
    selectedMessageIndices,
    setSelectedMessageIndices,
    updatePendingExcerpt,
    cancelPendingIngest,
    confirmPendingIngest,
    toggleMessageSelection,
  };
}

export function turnCanBeIngested(turn: ChatTurn | undefined): boolean {
  if (!turn || turn.kind === "error" || turn.kind === "status" || turn.streaming) return false;
  return Boolean(turn.content.trim());
}

function selectedMessagesTitle(turns: ChatTurn[], indices: number[]): string {
  const firstText = indices.map((index) => turns[index]?.content || "").find((content) => content.trim()) || "KnoArbor Chat";
  return buildExcerptTitle(firstText);
}

function selectedMessagesContent(turns: ChatTurn[], indices: number[]): string {
  return indices
    .map((index) => turns[index]?.content.trim() || "")
    .filter(Boolean)
    .join("\n\n");
}
