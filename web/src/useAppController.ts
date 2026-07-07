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
  getRuns,
  type ConfigSummary,
  type DoctorReport,
  type GraphResponse,
  type ModelProviderProbeState,
  type PageSummary,
  type QueryTrendResponse,
  type QueryResult,
  type ReportSummary,
  type UiStatusResponse,
} from "./api/client";
import { preloadRoute } from "./appRoutes";
import type { AppContext, AppNotice } from "./appContext";
import { useAppNavigation } from "./appNavigation";
import { useLanguagePreference, useSidebarPreference } from "./appPreferences";
import { useAppQueries } from "./appQueries";
import { useAppRefresh } from "./appRefresh";
import { readStoredModelProbeResults } from "./appRuntime";
import { translate } from "./i18n";
import { useDesktopCommands } from "./desktop/useDesktopCommands";
import { queryKeys } from "./queryKeys";
import type { ViewName } from "./types";
import type { RunRecord } from "./types";
import { nextValidVaultId } from "./vaultRuntime";

export function useAppController() {
  const [activeView, setActiveView] = useState<ViewName>("chat");
  const { language, setLanguage, t } = useLanguagePreference();
  const { sidebarCollapsed, toggleSidebar } = useSidebarPreference();
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [healthHint, setHealthHint] = useState(() => translate(language, "healthCheck"));
  const [configPath, setConfigPath] = useState<string | null>(null);
  const [configContent, setConfigContent] = useState("");
  const [configExists, setConfigExists] = useState(false);
  const [summary, setSummary] = useState<ConfigSummary>({});
  const [, setNotice] = useState<AppNotice | null>(null);
  const [queryResults, setQueryResults] = useState<QueryResult[]>([]);
  const [queryContextPack, setQueryContextPack] = useState("");
  const [workspaceSettingsOpen, setWorkspaceSettingsOpen] = useState(false);
  const [modelProbeResults, setModelProbeResultsState] = useState<Record<string, ModelProviderProbeState>>(() => readStoredModelProbeResults());
  const [selectedChatProvider, setSelectedChatProviderState] = useState(() => localStorage.getItem("knoarbor.chatProvider") || "");
  const [selectedVaultId, setSelectedVaultId] = useState(() =>
    localStorage.getItem("knoarbor.activeVaultId.userSet") === "true"
      ? localStorage.getItem("knoarbor.activeVaultId") || ""
      : "",
  );
  const previousActiveRunCountRef = useRef(0);
  const queryClient = useQueryClient();

  const {
    activeConcreteVault,
    activeRuns,
    activeVaultId,
    activeVaultSelector,
    configQuery,
    doctorReport,
    effectiveConfigPath,
    effectiveSummary,
    graph,
    healthQuery,
    modelProviders,
    needsRecentRuns,
    needsReports,
    needsVaultStatus,
    pages,
    queryTrend,
    recentRuns,
    reports,
    shouldPollRuns,
    status,
    vaultOptions,
    vaultOverviews,
    vaultPath,
  } = useAppQueries({
    activeView,
    configPath,
    selectedVaultId,
    summary,
    t,
  });
  const navigation = useAppNavigation({ activeVaultId, setActiveView, setSelectedVaultId });
  const { loadVaultState, refreshAll } = useAppRefresh({
    activeConcreteVault,
    activeView,
    effectiveConfigPath,
    needsRecentRuns,
    needsReports,
    needsVaultStatus,
    selectedVaultId,
    setNotice,
    shouldPollRuns,
    t,
  });

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
      for (const view of ["sources", "ingest", "lint", "query", "settings"] satisfies ViewName[]) {
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
    const next = nextValidVaultId(vaultOptions, selectedVaultId, effectiveSummary);
    if (next === selectedVaultId) return;
    if (localStorage.getItem("knoarbor.activeVaultId.userSet") === "true") {
      localStorage.setItem("knoarbor.activeVaultId", next);
    } else {
      localStorage.removeItem("knoarbor.activeVaultId");
    }
    setSelectedVaultId(next);
  }, [effectiveSummary, selectedVaultId, vaultOptions]);

  useEffect(() => {
    const previousRuns = previousActiveRunCountRef.current;
    previousActiveRunCountRef.current = activeRuns.length;
    if (previousRuns > 0 && activeRuns.length === 0) void loadVaultState();
  }, [activeRuns.length, loadVaultState]);

  const openWorkspaceSettings = useCallback(() => {
    setWorkspaceSettingsOpen(true);
  }, []);

  useDesktopCommands({
    onNewChat: navigation.openNewChat,
    onOpenSettings: openWorkspaceSettings,
    refreshAll,
    setNotice,
    t,
  });

  const setDoctorReportCached: Dispatch<SetStateAction<DoctorReport | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.doctor(configPath), (current: DoctorReport | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [configPath, queryClient]);

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
      doctorReport,
      graph,
      focusedPageId: navigation.focusedPageId,
      focusedWikiPath: navigation.focusedWikiPath,
      focusedReportPath: navigation.focusedReportPath,
      pendingChatPrompt: navigation.pendingChatPrompt,
      pendingChatSessionRequest: navigation.pendingChatSessionRequest,
      healthHint,
      pages,
      queryResults,
      queryContextPack,
      queryTrend,
      activeRuns,
      recentRuns,
      reports,
      serviceOnline,
      modelProviders,
      modelProbeResults,
      selectedChatProvider: selectedChatProvider || modelProviders?.default_provider || effectiveSummary.default_provider || "",
      setModelProbeResults,
      setSelectedChatProvider,
      setConfigContent,
      setConfigPath,
      setConfigExists,
      setDoctorReport: setDoctorReportCached,
      setNotice,
      setQueryResults,
      setQueryContextPack,
      setQueryTrend: setQueryTrendCached,
      setActiveRuns: setActiveRunsCached,
      setRecentRuns: setRecentRunsCached,
      setSummary,
      setStatus: setStatusCached,
      setGraph: setGraphCached,
      setPages: setPagesCached,
      setReports: setReportsCached,
      navigate: setActiveView,
      openPageInGraph: navigation.openPageInGraph,
      openWikiPage: navigation.openWikiPage,
      openWikiPageInVault: navigation.openWikiPageInVault,
      openChatWithPrompt: navigation.openChatWithPrompt,
      clearPendingChatPrompt: navigation.clearPendingChatPrompt,
      openChatSession: navigation.openChatSession,
      clearPendingChatSessionRequest: navigation.clearPendingChatSessionRequest,
      openReport: navigation.openReport,
      openSettings: openWorkspaceSettings,
      status,
      summary: effectiveSummary,
      activeVaultId,
      activeVaultSelector,
      vaultOptions,
      vaultOverviews,
      setActiveVaultId: navigation.setActiveVaultId,
      vaultPath,
      refreshAll,
      loadVaultState,
      language,
      setLanguage,
      t,
    }),
    [
      configPath,
      configContent,
      configExists,
      doctorReport,
      graph,
      navigation.focusedPageId,
      navigation.pendingChatPrompt,
      navigation.pendingChatSessionRequest,
      navigation.focusedReportPath,
      navigation.focusedWikiPath,
      healthHint,
      pages,
      queryResults,
      queryContextPack,
      queryTrend,
      activeRuns,
      recentRuns,
      reports,
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
      vaultOptions,
      vaultOverviews,
      navigation.setActiveVaultId,
      vaultPath,
      refreshAll,
      loadVaultState,
      language,
      setLanguage,
      navigation.openPageInGraph,
      navigation.openWikiPage,
      navigation.openWikiPageInVault,
      navigation.openChatWithPrompt,
      navigation.clearPendingChatPrompt,
      navigation.openChatSession,
      navigation.clearPendingChatSessionRequest,
      navigation.openReport,
      openWorkspaceSettings,
      setDoctorReportCached,
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
    setActiveView,
    setWorkspaceSettingsOpen,
    sidebarCollapsed,
    t,
    toggleSidebar,
    workspaceSettingsOpen,
  };
}
