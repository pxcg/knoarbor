import { useCallback, useState, type Dispatch, type SetStateAction } from "react";

import type { PendingChatSessionRequest } from "./appContext";
import type { ViewName } from "./types";

type AppNavigationInput = {
  activeVaultId: string;
  setActiveView: Dispatch<SetStateAction<ViewName>>;
  setSelectedVaultId: Dispatch<SetStateAction<string>>;
};

export function useAppNavigation({ activeVaultId, setActiveView, setSelectedVaultId }: AppNavigationInput) {
  const [focusedPageId, setFocusedPageId] = useState<string | null>(null);
  const [focusedWikiPath, setFocusedWikiPath] = useState<string | null>(null);
  const [pendingChatPrompt, setPendingChatPrompt] = useState("");
  const [pendingChatSessionRequest, setPendingChatSessionRequest] = useState<PendingChatSessionRequest | null>(null);
  const [focusedReportPath, setFocusedReportPath] = useState<string | null>(null);

  const clearTargets = useCallback(() => {
    setFocusedPageId(null);
    setFocusedWikiPath(null);
    setFocusedReportPath(null);
  }, []);

  const selectVaultForNavigation = useCallback((vaultId?: string | null) => {
    if (!vaultId || vaultId === activeVaultId) return;
    localStorage.setItem("knoarbor.activeVaultId", vaultId);
    localStorage.setItem("knoarbor.activeVaultId.userSet", "true");
    setSelectedVaultId(vaultId);
  }, [activeVaultId, setSelectedVaultId]);

  const setActiveVaultId = useCallback((next: string) => {
    localStorage.setItem("knoarbor.activeVaultId", next);
    localStorage.setItem("knoarbor.activeVaultId.userSet", "true");
    setSelectedVaultId(next);
    clearTargets();
  }, [clearTargets, setSelectedVaultId]);

  const openNewChat = useCallback(() => {
    setPendingChatPrompt("");
    clearTargets();
    setActiveView("chat");
  }, [clearTargets, setActiveView]);

  const openPageInGraph = useCallback((pageId: string) => {
    setFocusedPageId(pageId);
    setActiveView("graph");
  }, [setActiveView]);

  const openReport = useCallback((path: string) => {
    setFocusedReportPath(path);
    setActiveView("reports");
  }, [setActiveView]);

  const openWikiPage = useCallback((path: string) => {
    setFocusedWikiPath(path);
    setActiveView("wiki");
  }, [setActiveView]);

  const openWikiPageInVault = useCallback((vaultId: string | null | undefined, path: string) => {
    selectVaultForNavigation(vaultId);
    setFocusedPageId(null);
    setFocusedReportPath(null);
    setFocusedWikiPath(path);
    setActiveView("wiki");
  }, [selectVaultForNavigation, setActiveView]);

  const openChatWithPrompt = useCallback((prompt: string, vaultId?: string | null) => {
    selectVaultForNavigation(vaultId);
    clearTargets();
    setPendingChatPrompt(prompt);
    setActiveView("chat");
  }, [clearTargets, selectVaultForNavigation, setActiveView]);

  const clearPendingChatPrompt = useCallback(() => {
    setPendingChatPrompt("");
  }, []);

  const openChatSession = useCallback((sessionId: string | null, vaultId?: string | null) => {
    selectVaultForNavigation(vaultId);
    clearTargets();
    setPendingChatSessionRequest({ sessionId, vaultId: vaultId || null, requestId: Date.now() });
    setActiveView("chat");
  }, [clearTargets, selectVaultForNavigation, setActiveView]);

  const clearPendingChatSessionRequest = useCallback(() => {
    setPendingChatSessionRequest(null);
  }, []);

  return {
    clearPendingChatPrompt,
    clearPendingChatSessionRequest,
    focusedPageId,
    focusedReportPath,
    focusedWikiPath,
    openChatSession,
    openChatWithPrompt,
    openNewChat,
    openPageInGraph,
    openReport,
    openWikiPage,
    openWikiPageInVault,
    pendingChatPrompt,
    pendingChatSessionRequest,
    setActiveVaultId,
  };
}
