import { useCallback, useRef, useState, type Dispatch, type SetStateAction } from "react";

import type { ViewName } from "./types";
import type { RunRecord } from "./types";

export type AppNavigationTarget =
  | { kind: "wiki-page"; path: string; vaultId: string; requestId: number }
  | { kind: "graph-page"; pageId: string; vaultId: string; requestId: number }
  | { kind: "report"; path: string; vaultId: string; requestId: number }
  | { kind: "run"; runId: string; vaultId: string; flow: RunRecord["flow"]; requestId: number }
  | { kind: "chat-prompt"; prompt: string; vaultId: string; requestId: number }
  | { kind: "chat-session"; sessionId: string | null; vaultId: string; requestId: number };

type AppNavigationInput = {
  activeView: ViewName;
  activeVaultId: string;
  chatScopeVaultId: string;
  setActiveView: Dispatch<SetStateAction<ViewName>>;
  setChatScopeVaultId: (value: string) => void;
  setSelectedVaultId: Dispatch<SetStateAction<string>>;
};

export function useAppNavigation({
  activeView,
  activeVaultId,
  chatScopeVaultId,
  setActiveView,
  setChatScopeVaultId,
  setSelectedVaultId,
}: AppNavigationInput) {
  const [target, setTarget] = useState<AppNavigationTarget | null>(null);
  const requestSequence = useRef(0);
  const activeViewRef = useRef(activeView);
  activeViewRef.current = activeView;

  const selectViewVault = useCallback((view: ViewName, vaultId?: string | null) => {
    if (!vaultId || vaultId === "all" || view === "chat" || view === "query") return;
    localStorage.setItem(pageVaultStorageKey(view), vaultId);
    localStorage.setItem("knoarbor.workspaceVaultId", vaultId);
    setSelectedVaultId(vaultId);
  }, [setSelectedVaultId]);

  const nextRequestId = useCallback(() => {
    requestSequence.current += 1;
    return requestSequence.current;
  }, []);

  const selectWorkspaceVault = useCallback((vaultId?: string | null) => {
    if (!vaultId || vaultId === "all" || vaultId === activeVaultId) return;
    localStorage.setItem("knoarbor.workspaceVaultId", vaultId);
    setSelectedVaultId(vaultId);
  }, [activeVaultId, setSelectedVaultId]);

  const selectChatScope = useCallback((vaultId?: string | null) => {
    if (!vaultId || vaultId === chatScopeVaultId) return;
    localStorage.setItem("knoarbor.chatScopeVaultId", vaultId);
    setChatScopeVaultId(vaultId);
  }, [chatScopeVaultId, setChatScopeVaultId]);

  const navigate = useCallback((view: ViewName) => {
    setTarget(null);
    const pageVaultId = storedPageVaultId(view) || activeVaultId;
    selectViewVault(view, pageVaultId);
    activeViewRef.current = view;
    setActiveView(view);
  }, [activeVaultId, selectViewVault, setActiveView]);

  const setActiveVaultId = useCallback((next: string) => {
    if (!next || next === "all") return;
    selectViewVault(activeViewRef.current, next);
    setTarget(null);
  }, [selectViewVault]);

  const openNewChat = useCallback(() => {
    const vaultId = chatScopeVaultId || activeVaultId;
    setTarget({ kind: "chat-session", sessionId: null, vaultId, requestId: nextRequestId() });
    setActiveView("chat");
  }, [activeVaultId, chatScopeVaultId, nextRequestId, setActiveView]);

  const openPageInGraph = useCallback((pageId: string, vaultId = activeVaultId) => {
    selectViewVault("graph", vaultId);
    selectWorkspaceVault(vaultId);
    setTarget({ kind: "graph-page", pageId, vaultId, requestId: nextRequestId() });
    setActiveView("graph");
  }, [activeVaultId, nextRequestId, selectViewVault, selectWorkspaceVault, setActiveView]);

  const openReport = useCallback((path: string, vaultId = activeVaultId) => {
    selectViewVault("reports", vaultId);
    selectWorkspaceVault(vaultId);
    setTarget({ kind: "report", path, vaultId, requestId: nextRequestId() });
    setActiveView("reports");
  }, [activeVaultId, nextRequestId, selectViewVault, selectWorkspaceVault, setActiveView]);

  const openRun = useCallback((runId: string, vaultId: string, flow: RunRecord["flow"]) => {
    selectViewVault(flow === "lint" ? "lint" : "ingest", vaultId);
    selectWorkspaceVault(vaultId);
    setTarget({ kind: "run", runId, vaultId, flow, requestId: nextRequestId() });
    setActiveView(flow === "lint" ? "lint" : "ingest");
  }, [nextRequestId, selectViewVault, selectWorkspaceVault, setActiveView]);

  const openWikiPage = useCallback((path: string) => {
    selectViewVault("wiki", activeVaultId);
    setTarget({ kind: "wiki-page", path, vaultId: activeVaultId, requestId: nextRequestId() });
    setActiveView("wiki");
  }, [activeVaultId, nextRequestId, selectViewVault, setActiveView]);

  const openWikiPageInVault = useCallback((vaultId: string | null | undefined, path: string) => {
    const targetVaultId = vaultId && vaultId !== "all" ? vaultId : activeVaultId;
    selectViewVault("wiki", targetVaultId);
    selectWorkspaceVault(targetVaultId);
    setTarget({ kind: "wiki-page", path, vaultId: targetVaultId, requestId: nextRequestId() });
    setActiveView("wiki");
  }, [activeVaultId, nextRequestId, selectViewVault, selectWorkspaceVault, setActiveView]);

  const openChatWithPrompt = useCallback((prompt: string, vaultId?: string | null) => {
    const targetVaultId = vaultId || chatScopeVaultId || activeVaultId;
    selectChatScope(targetVaultId);
    setTarget({ kind: "chat-prompt", prompt, vaultId: targetVaultId, requestId: nextRequestId() });
    setActiveView("chat");
  }, [activeVaultId, chatScopeVaultId, nextRequestId, selectChatScope, setActiveView]);

  const openChatSession = useCallback((sessionId: string | null, vaultId?: string | null) => {
    const targetVaultId = vaultId || chatScopeVaultId || activeVaultId;
    selectChatScope(targetVaultId);
    setTarget({ kind: "chat-session", sessionId, vaultId: targetVaultId, requestId: nextRequestId() });
    setActiveView("chat");
  }, [activeVaultId, chatScopeVaultId, nextRequestId, selectChatScope, setActiveView]);

  const consumeTarget = useCallback((requestId: number) => {
    setTarget((current) => current?.requestId === requestId ? null : current);
  }, []);

  return {
    consumeTarget,
    navigate,
    openChatSession,
    openChatWithPrompt,
    openNewChat,
    openPageInGraph,
    openReport,
    openRun,
    openWikiPage,
    openWikiPageInVault,
    setActiveVaultId,
    target,
  };
}

export function pageVaultStorageKey(view: ViewName): string {
  return `knoarbor.pageVaultId.${view}`;
}

export function storedPageVaultId(view: ViewName): string {
  if (view === "chat" || view === "query") return "";
  return localStorage.getItem(pageVaultStorageKey(view)) || "";
}
