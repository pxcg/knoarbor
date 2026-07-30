import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getPages,
  getGraph,
  getQueryTrends,
  getRun,
  getRuns,
  type ConfigSummary,
  type GraphResponse,
  type ModelProviderProbeState,
  type PageSummary,
  type QueryTrendResponse,
  type ReportSummary,
  type UiStatusResponse,
} from "./api/client";
import { preloadRoute } from "./appRoutes";
import type { AppContext } from "./appContext";
import { pageVaultStorageKey, storedPageVaultId, useAppNavigation } from "./appNavigation";
import { useAppearancePreference, useLanguagePreference, useSidebarPreference } from "./appPreferences";
import { useAppQueries } from "./appQueries";
import { useAppRefresh } from "./appRefresh";
import { readStoredModelProbeResults } from "./appRuntime";
import { translate } from "./i18n";
import { useDesktopCommands } from "./desktop/useDesktopCommands";
import { queryKeys } from "./queryKeys";
import type { ViewName } from "./types";
import type { RunRecord } from "./types";
import { buildVaultSelector, nextValidChatScopeVaultId, nextValidWorkspaceVaultId } from "./vaultRuntime";

export function useAppController() {
  const [activeView, setActiveView] = useState<ViewName>("chat");
  const { language, setLanguage, t } = useLanguagePreference();
  const { appearanceMode, setAppearanceMode } = useAppearancePreference();
  const { sidebarCollapsed, toggleSidebar } = useSidebarPreference();
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [healthHint, setHealthHint] = useState(() => translate(language, "healthCheck"));
  const [configPath, setConfigPath] = useState<string | null>(null);
  const [configContent, setConfigContent] = useState("");
  const [configExists, setConfigExists] = useState(false);
  const [summary, setSummary] = useState<ConfigSummary>({});
  const [workspaceSettingsOpen, setWorkspaceSettingsOpen] = useState(false);
  const [modelProbeResults, setModelProbeResultsState] = useState<Record<string, ModelProviderProbeState>>(() => readStoredModelProbeResults());
  const [selectedChatProvider, setSelectedChatProviderState] = useState(() => localStorage.getItem("knoarbor.chatProvider") || "");
  const [selectedVaultId, setSelectedVaultId] = useState(() => localStorage.getItem("knoarbor.workspaceVaultId") || "");
  const [chatScopeVaultId, setChatScopeVaultIdState] = useState(() => localStorage.getItem("knoarbor.chatScopeVaultId") || "all");
  const previousActiveRunsRef = useRef({ vaultId: "", count: 0 });
  const refreshedTerminalRunsRef = useRef(new Set<string>());
  const watchedRunsRef = useRef(new Set<string>());
  const runWatchTimersRef = useRef(new Map<string, number>());
  const queryClient = useQueryClient();

  const {
    activeConcreteVault,
    activeRuns,
    activeVaultId,
    activeVaultSelector,
    configQuery,
    effectiveConfigPath,
    effectiveSummary,
    graph,
    graphReady,
    healthQuery,
    modelProviders,
    needsRecentRuns,
    needsReports,
    needsVaultStatus,
    pages,
    pagesReady,
    queryTrend,
    recentRuns,
    reports,
    reportsReady,
    shouldPollRuns,
    status,
    vaultOptions,
    vaultRegistryReady,
    vaultPath,
  } = useAppQueries({
    activeView,
    configPath,
    selectedVaultId,
    summary,
  });
  const setChatScopeVaultId = useCallback((next: string) => {
    localStorage.setItem("knoarbor.chatScopeVaultId", next);
    setChatScopeVaultIdState(next);
  }, []);
  const navigation = useAppNavigation({
    activeView,
    activeVaultId,
    chatScopeVaultId,
    setActiveView,
    setChatScopeVaultId,
    setSelectedVaultId,
  });
  const { loadVaultState, refreshAll } = useAppRefresh({
    activeConcreteVault,
    activeView,
    effectiveConfigPath,
    needsRecentRuns,
    needsReports,
    needsVaultStatus,
    selectedVaultId,
    shouldPollRuns,
  });

  const refreshAfterRunTerminal = useCallback(async (run: RunRecord) => {
    const vault = vaultOptions.find((item) => (
      (run.vault_id && item.id === run.vault_id)
      || (run.vault_path && item.path === run.vault_path)
    )) || activeConcreteVault;
    const refreshKey = `${vault.id}:${run.run_id}`;
    if (refreshedTerminalRunsRef.current.has(refreshKey)) return;
    refreshedTerminalRunsRef.current.add(refreshKey);

    const refreshTasks: Promise<unknown>[] = [
      loadVaultState(vault, {
        activeRuns: true,
        recentRuns: true,
        reports: true,
        status: true,
      }),
    ];
    if (run.flow === "ingest") {
      refreshTasks.push(
        queryClient.invalidateQueries({ queryKey: queryKeys.pages(vault.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.graph(vault.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.queryTrends(vault.id) }),
      );
    }
    await Promise.all(refreshTasks);
  }, [activeConcreteVault, loadVaultState, queryClient, vaultOptions]);

  const watchRunToTerminal = useCallback((runId: string, vaultId?: string | null) => {
    const vault = vaultOptions.find((item) => item.id === vaultId) || activeConcreteVault;
    const watchKey = `${vault.id}:${runId}`;
    if (watchedRunsRef.current.has(watchKey)) return;
    watchedRunsRef.current.add(watchKey);
    const selector = buildVaultSelector(effectiveConfigPath, vault);

    const poll = async () => {
      try {
        const run = await getRun(selector, runId);
        if (["completed", "failed", "cancelled", "partially_failed"].includes(run.status)) {
          watchedRunsRef.current.delete(watchKey);
          runWatchTimersRef.current.delete(watchKey);
          await refreshAfterRunTerminal(run);
          return;
        }
      } catch (error) {
        console.error("Tracked run refresh failed", error);
      }
      const timer = window.setTimeout(() => void poll(), 1000);
      runWatchTimersRef.current.set(watchKey, timer);
    };
    void poll();
  }, [activeConcreteVault, effectiveConfigPath, refreshAfterRunTerminal, vaultOptions]);

  useEffect(() => () => {
    for (const timer of runWatchTimersRef.current.values()) window.clearTimeout(timer);
    runWatchTimersRef.current.clear();
    watchedRunsRef.current.clear();
  }, []);

  const setModelProbeResults: Dispatch<SetStateAction<Record<string, ModelProviderProbeState>>> = useCallback((value) => {
    setModelProbeResultsState((current) => {
      const next = typeof value === "function" ? value(current) : value;
      localStorage.setItem("knoarbor.modelProbeResults", JSON.stringify(next));
      return next;
    });
  }, []);

  const setSelectedChatProvider = useCallback((next: string) => {
    if (next) localStorage.setItem("knoarbor.chatProvider", next);
    else localStorage.removeItem("knoarbor.chatProvider");
    setSelectedChatProviderState(next);
  }, []);

  useEffect(() => {
    const preloadCommonRoutes = () => {
      for (const view of ["ingest", "lint", "query"] satisfies ViewName[]) {
        preloadRoute(view);
      }
    };
    const timer = window.setTimeout(preloadCommonRoutes, 1200);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!workspaceSettingsOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setWorkspaceSettingsOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [workspaceSettingsOpen]);

  useEffect(() => {
    if (healthQuery.isSuccess) {
      setServiceOnline(true);
      setHealthHint(healthQuery.data.status ? t("healthReachable") : t("healthResponded"));
    } else if (healthQuery.isError) {
      setServiceOnline(false);
      setHealthHint(healthQuery.error instanceof Error ? healthQuery.error.message : t("healthFailed"));
    }
  }, [healthQuery.data, healthQuery.error, healthQuery.isError, healthQuery.isSuccess, t]);

  useEffect(() => {
    if (!configQuery.data) return;
    setConfigPath(configQuery.data.config_path);
    setConfigContent(configQuery.data.content);
    setConfigExists(configQuery.data.exists);
    setSummary(configQuery.data.summary || {});
  }, [configQuery.data]);

  useEffect(() => {
    if (!vaultOptions.length) return;
    const next = nextValidWorkspaceVaultId(vaultOptions, selectedVaultId, effectiveSummary);
    if (next === selectedVaultId) return;
    localStorage.setItem("knoarbor.workspaceVaultId", next);
    setSelectedVaultId(next);
  }, [effectiveSummary, selectedVaultId, vaultOptions]);

  useEffect(() => {
    if (!vaultRegistryReady || !vaultOptions.length) return;
    const next = nextValidChatScopeVaultId(vaultOptions, chatScopeVaultId, activeVaultId);
    if (next !== chatScopeVaultId) setChatScopeVaultId(next);
  }, [activeVaultId, chatScopeVaultId, setChatScopeVaultId, vaultOptions, vaultRegistryReady]);

  useEffect(() => {
    if (activeView === "chat" || activeView === "query" || !activeVaultId || activeVaultId === "all") return;
    if (!storedPageVaultId(activeView)) {
      localStorage.setItem(pageVaultStorageKey(activeView), activeVaultId);
    }
  }, [activeVaultId, activeView]);

  const chatScopeVaultSelector = useMemo(() => {
    const selected = vaultOptions.find((vault) => vault.id === chatScopeVaultId);
    if (selected) return buildVaultSelector(effectiveConfigPath, selected);
    return activeVaultSelector;
  }, [activeVaultSelector, chatScopeVaultId, effectiveConfigPath, vaultOptions]);

  useEffect(() => {
    const previous = previousActiveRunsRef.current;
    previousActiveRunsRef.current = { vaultId: activeVaultId, count: activeRuns.length };
    if (previous.vaultId !== activeVaultId || previous.count === 0 || activeRuns.length > 0) return;
    void loadVaultState();
  }, [activeRuns.length, activeVaultId, loadVaultState]);

  useEffect(() => {
    const terminalIngest = recentRuns.find((run) => (
      run.flow === "ingest"
      && ["completed", "failed", "cancelled", "partially_failed"].includes(run.status)
    ));
    if (terminalIngest) void refreshAfterRunTerminal(terminalIngest);
  }, [recentRuns, refreshAfterRunTerminal]);

  const openWorkspaceSettings = useCallback(() => {
    setWorkspaceSettingsOpen(true);
  }, []);

  useDesktopCommands({
    onNewChat: navigation.openNewChat,
    onOpenSettings: openWorkspaceSettings,
    refreshAll,
  });

  const setStatusCached: Dispatch<SetStateAction<UiStatusResponse | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.status(activeVaultId), (current: UiStatusResponse | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [activeVaultId, queryClient]);

  const setGraphCached: Dispatch<SetStateAction<GraphResponse | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.graph(activeVaultId), (current: GraphResponse | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [activeVaultId, queryClient]);

  const setPagesCached: Dispatch<SetStateAction<PageSummary[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.pages(activeVaultId), (current: { vault_path: string; pages: PageSummary[] } | undefined) => {
      const pagesValue = typeof value === "function" ? value(current?.pages || []) : value;
      return { vault_path: vaultPath, pages: pagesValue };
    });
  }, [activeVaultId, queryClient, vaultPath]);

  const setReportsCached: Dispatch<SetStateAction<ReportSummary[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.reports(activeVaultId), (current: { vault_path: string; reports: ReportSummary[] } | undefined) => {
      const reportsValue = typeof value === "function" ? value(current?.reports || []) : value;
      return { vault_path: vaultPath, reports: reportsValue };
    });
  }, [activeVaultId, queryClient, vaultPath]);

  const setQueryTrendCached: Dispatch<SetStateAction<QueryTrendResponse | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.queryTrends(activeVaultId), (current: QueryTrendResponse | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [activeVaultId, queryClient]);

  const setActiveRunsCached: Dispatch<SetStateAction<RunRecord[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.activeRuns(activeVaultId), (current: { runs: RunRecord[] } | undefined) => {
      const runsValue = typeof value === "function" ? value(current?.runs || []) : value;
      return { runs: runsValue };
    });
  }, [activeVaultId, queryClient]);

  const setRecentRunsCached: Dispatch<SetStateAction<RunRecord[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.recentRuns(activeVaultId), (current: { runs: RunRecord[] } | undefined) => {
      const runsValue = typeof value === "function" ? value(current?.runs || []) : value;
      return { runs: runsValue };
    });
  }, [activeVaultId, queryClient]);

  const preloadView = useCallback((view: ViewName) => {
    preloadRoute(view);
    if (view === "graph") void queryClient.prefetchQuery({ queryKey: queryKeys.graph(activeVaultId), queryFn: () => getGraph(vaultPath), staleTime: 60_000 });
    if (view === "wiki") void queryClient.prefetchQuery({ queryKey: queryKeys.pages(activeVaultId), queryFn: () => getPages(activeVaultSelector), staleTime: 60_000 });
    if (view === "query") void queryClient.prefetchQuery({ queryKey: queryKeys.queryTrends(activeVaultId), queryFn: () => getQueryTrends(activeVaultSelector), staleTime: 60_000 });
    if (view === "ingest" || view === "lint" || view === "reports") void queryClient.prefetchQuery({ queryKey: queryKeys.recentRuns(activeVaultId), queryFn: () => getRuns(activeVaultSelector, false, 12), staleTime: 20_000 });
  }, [activeVaultId, activeVaultSelector, queryClient, vaultPath]);

  const context: AppContext = useMemo(
    () => ({
      configPath,
      configContent,
      configExists,
      graph,
      graphReady,
      navigationTarget: navigation.target,
      consumeNavigationTarget: navigation.consumeTarget,
      healthHint,
      pages,
      pagesReady,
      queryTrend,
      activeRuns,
      recentRuns,
      reports,
      reportsReady,
      serviceOnline,
      modelProviders,
      modelProbeResults,
      selectedChatProvider: selectedChatProvider || modelProviders?.default_provider || effectiveSummary.default_provider || "",
      setModelProbeResults,
      setSelectedChatProvider,
      setConfigContent,
      setConfigPath,
      setConfigExists,
      setQueryTrend: setQueryTrendCached,
      setActiveRuns: setActiveRunsCached,
      setRecentRuns: setRecentRunsCached,
      setSummary,
      setStatus: setStatusCached,
      setGraph: setGraphCached,
      setPages: setPagesCached,
      setReports: setReportsCached,
      navigate: navigation.navigate,
      openPageInGraph: navigation.openPageInGraph,
      openWikiPage: navigation.openWikiPage,
      openWikiPageInVault: navigation.openWikiPageInVault,
      openChatWithPrompt: navigation.openChatWithPrompt,
      openChatSession: navigation.openChatSession,
      openReport: navigation.openReport,
      openRun: navigation.openRun,
      openSettings: openWorkspaceSettings,
      status,
      summary: effectiveSummary,
      activeVaultId,
      activeVaultSelector,
      chatScopeVaultId,
      chatScopeVaultSelector,
      vaultOptions,
      setActiveVaultId: navigation.setActiveVaultId,
      setChatScopeVaultId,
      vaultPath,
      refreshAll,
      loadVaultState,
      refreshAfterRunTerminal,
      watchRunToTerminal,
      language,
      setLanguage,
      appearanceMode,
      setAppearanceMode,
      t,
    }),
    [
      configPath,
      configContent,
      configExists,
      graph,
      graphReady,
      navigation.target,
      navigation.consumeTarget,
      healthHint,
      pages,
      pagesReady,
      queryTrend,
      activeRuns,
      recentRuns,
      reports,
      reportsReady,
      serviceOnline,
      modelProviders,
      modelProbeResults,
      selectedChatProvider,
      setModelProbeResults,
      setSelectedChatProvider,
      status,
      effectiveSummary,
      activeVaultId,
      activeVaultSelector,
      chatScopeVaultId,
      chatScopeVaultSelector,
      vaultOptions,
      navigation.setActiveVaultId,
      setChatScopeVaultId,
      vaultPath,
      refreshAll,
      loadVaultState,
      refreshAfterRunTerminal,
      watchRunToTerminal,
      language,
      setLanguage,
      appearanceMode,
      setAppearanceMode,
      navigation.openPageInGraph,
      navigation.openWikiPage,
      navigation.openWikiPageInVault,
      navigation.openChatWithPrompt,
      navigation.openChatSession,
      navigation.openReport,
      navigation.openRun,
      navigation.navigate,
      openWorkspaceSettings,
      setStatusCached,
      setGraphCached,
      setPagesCached,
      setReportsCached,
      setQueryTrendCached,
      setActiveRunsCached,
      setRecentRunsCached,
      t,
    ],
  );

  return {
    activeView,
    context,
    language,
    preloadView,
    serviceOnline,
    setActiveView: navigation.navigate,
    setWorkspaceSettingsOpen,
    sidebarCollapsed,
    t,
    toggleSidebar,
    workspaceSettingsOpen,
  };
}
