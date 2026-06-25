import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { keepPreviousData, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getConfig,
  getDoctor,
  getPages,
  getGraph,
  getHealth,
  getModelProviders,
  getVaults,
  getQueryTrends,
  getActiveRuns,
  getRuns,
  getReports,
  getStatus,
  type ConfigSummary,
  type DoctorReport,
  type GraphResponse,
  type ModelProviderProbeState,
  type ModelProvidersResponse,
  type PageSummary,
  type QueryTrendResponse,
  type QueryResult,
  type ReportSummary,
  type UiStatusResponse,
  type VaultSelector,
} from "./api/client";
import { AppShell } from "./components/AppShell";
import { LoadingBlock } from "./components/LoadingBlock";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { SidebarRecentSessions } from "./components/SidebarRecentSessions";
import { WorkspaceSettingsModal } from "./components/WorkspaceSettingsModal";
import { detectLanguage, translate } from "./i18n";
import { queryKeys } from "./queryKeys";
import type { Language, ViewName } from "./types";
import type { RunRecord } from "./types";
import { buildVaultOptions, buildVaultSelector, concreteVaultOptions, nextValidVaultId, resolveActiveVault, resolveConcreteVault, type VaultOption, type VaultOverview } from "./vaultRuntime";

const loadChatPage = () => import("./pages/ChatPage").then((module) => ({ default: module.ChatPage }));
const loadOverviewPage = () => import("./pages/OverviewPage").then((module) => ({ default: module.OverviewPage }));
const loadRunsPage = () => import("./pages/RunsPage").then((module) => ({ default: module.RunsPage }));
const loadSourcesPage = () => import("./pages/SourcesPage").then((module) => ({ default: module.SourcesPage }));
const loadIngestPage = () => import("./pages/IngestPage").then((module) => ({ default: module.IngestPage }));
const loadLintPage = () => import("./pages/LintPage").then((module) => ({ default: module.LintPage }));
const loadQueryPage = () => import("./pages/QueryPage").then((module) => ({ default: module.QueryPage }));
const loadWikiPage = () => import("./pages/WikiPage").then((module) => ({ default: module.WikiPage }));
const loadGraphPage = () => import("./pages/GraphPage").then((module) => ({ default: module.GraphPage }));
const loadReportsPage = () => import("./pages/ReportsPage").then((module) => ({ default: module.ReportsPage }));
const loadTokensPage = () => import("./pages/TokensPage").then((module) => ({ default: module.TokensPage }));
const loadConfigPage = () => import("./pages/ConfigPage").then((module) => ({ default: module.ConfigPage }));
const loadDocsPage = () => import("./pages/DocsPage").then((module) => ({ default: module.DocsPage }));

const routePreloaders = {
  chat: loadChatPage,
  overview: loadOverviewPage,
  runs: loadRunsPage,
  sources: loadSourcesPage,
  ingest: loadIngestPage,
  lint: loadLintPage,
  query: loadQueryPage,
  wiki: loadWikiPage,
  graph: loadGraphPage,
  reports: loadReportsPage,
  tokens: loadTokensPage,
  settings: loadConfigPage,
  docs: loadDocsPage,
} satisfies Record<ViewName, () => Promise<unknown>>;

const preloadedRoutes = new Set<ViewName>();

function preloadRoute(view: ViewName) {
  if (preloadedRoutes.has(view)) return;
  preloadedRoutes.add(view);
  void routePreloaders[view]().catch(() => {
    preloadedRoutes.delete(view);
  });
}

const ChatPage = lazy(loadChatPage);
const OverviewPage = lazy(loadOverviewPage);
const RunsPage = lazy(loadRunsPage);
const SourcesPage = lazy(loadSourcesPage);
const IngestPage = lazy(loadIngestPage);
const LintPage = lazy(loadLintPage);
const QueryPage = lazy(loadQueryPage);
const WikiPage = lazy(loadWikiPage);
const GraphPage = lazy(loadGraphPage);
const ReportsPage = lazy(loadReportsPage);
const TokensPage = lazy(loadTokensPage);
const ConfigPage = lazy(loadConfigPage);
const DocsPage = lazy(loadDocsPage);

export type AppNotice = {
  message: string;
  error?: boolean;
  actionLabel?: string;
  onAction?: () => void;
};

export function App() {
  const [activeView, setActiveView] = useState<ViewName>("chat");
  const [language, setLanguageState] = useState<Language>(() => detectLanguage());
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [healthHint, setHealthHint] = useState(() => translate(detectLanguage(), "healthCheck"));
  const [configPath, setConfigPath] = useState<string | null>(null);
  const [configContent, setConfigContent] = useState("");
  const [configExists, setConfigExists] = useState(false);
  const [summary, setSummary] = useState<ConfigSummary>({});
  const [, setNotice] = useState<AppNotice | null>(null);
  const [queryResults, setQueryResults] = useState<QueryResult[]>([]);
  const [queryContextPack, setQueryContextPack] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [focusedPageId, setFocusedPageId] = useState<string | null>(null);
  const [focusedWikiPath, setFocusedWikiPath] = useState<string | null>(null);
  const [pendingChatPrompt, setPendingChatPrompt] = useState("");
  const [pendingChatSessionRequest, setPendingChatSessionRequest] = useState<PendingChatSessionRequest | null>(null);
  const [focusedReportPath, setFocusedReportPath] = useState<string | null>(null);
  const [workspaceSettingsOpen, setWorkspaceSettingsOpen] = useState(false);
  const [modelProbeResults, setModelProbeResultsState] = useState<Record<string, ModelProviderProbeState>>(() => readStoredModelProbeResults());
  const [selectedChatProvider, setSelectedChatProviderState] = useState(() => localStorage.getItem("knoarbor.chatProvider") || "");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("knoarbor.sidebarCollapsed") === "true");
  const [selectedVaultId, setSelectedVaultId] = useState(() =>
    localStorage.getItem("knoarbor.activeVaultId.userSet") === "true"
      ? localStorage.getItem("knoarbor.activeVaultId") || ""
      : "",
  );
  const previousActiveRunCountRef = useRef(0);
  const queryClient = useQueryClient();

  const t = useCallback((key: string) => translate(language, key), [language]);
  const isRunView = activeView === "runs" || activeView === "ingest" || activeView === "lint";
  const needsVaultStatus = activeView === "overview" || activeView === "sources";
  const needsReports = activeView === "overview" || activeView === "runs" || activeView === "reports";
  const needsRecentRuns = activeView === "overview" || isRunView;
  const needsVaultOverview = activeView === "overview" || activeView === "runs" || activeView === "reports";
  const shouldPollRuns = activeView === "overview" || isRunView;

  const healthQuery = useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const configQuery = useQuery({
    queryKey: queryKeys.config,
    queryFn: getConfig,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const effectiveConfigPath = configQuery.data?.config_path ?? configPath;
  const effectiveSummary = configQuery.data?.summary || summary;
  const modelProvidersQuery = useQuery({
    queryKey: queryKeys.modelProviders(effectiveConfigPath),
    queryFn: () => getModelProviders(effectiveConfigPath),
    enabled: configQuery.isSuccess,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
  const vaultsQuery = useQuery({
    queryKey: queryKeys.vaults(effectiveConfigPath),
    queryFn: () => getVaults(effectiveConfigPath),
    enabled: configQuery.isSuccess,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
  const vaultOptions = useMemo(() => buildVaultOptions(effectiveSummary, vaultsQuery.data), [effectiveSummary, vaultsQuery.data]);
  const activeVault = useMemo(() => resolveActiveVault(vaultOptions, selectedVaultId, effectiveSummary), [effectiveSummary, selectedVaultId, vaultOptions]);
  const concreteOptions = useMemo(() => concreteVaultOptions(vaultOptions), [vaultOptions]);
  const activeConcreteVault = useMemo(() => resolveConcreteVault(vaultOptions, selectedVaultId, effectiveSummary), [effectiveSummary, selectedVaultId, vaultOptions]);
  const vaultPath = activeConcreteVault.path;
  const activeVaultId = activeVault.id;
  const activeVaultSelector = useMemo(() => buildVaultSelector(effectiveConfigPath, activeConcreteVault), [activeConcreteVault, effectiveConfigPath]);

  const doctorQuery = useQuery({
    queryKey: queryKeys.doctor(effectiveConfigPath),
    queryFn: () => getDoctor(effectiveConfigPath, { checkModelRuntime: false, checkConnectorRuntime: false }),
    enabled: configQuery.isSuccess && activeView === "overview",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const statusQuery = useQuery({
    queryKey: queryKeys.status(activeVaultId),
    queryFn: () => getStatus(vaultPath),
    enabled: configQuery.isSuccess && Boolean(vaultPath) && needsVaultStatus,
    staleTime: 20_000,
    placeholderData: keepPreviousData,
  });

  const reportsQuery = useQuery({
    queryKey: queryKeys.reports(activeVaultId),
    queryFn: () => getReports(activeVaultSelector),
    enabled: configQuery.isSuccess && Boolean(vaultPath) && needsReports,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const activeRunsQuery = useQuery({
    queryKey: queryKeys.activeRuns(activeVaultId),
    queryFn: () => getActiveRuns(activeVaultSelector),
    enabled: configQuery.isSuccess && Boolean(vaultPath),
    refetchInterval: (query) => {
      const runs = query.state.data?.runs || [];
      return shouldPollRuns || runs.length > 0 ? 2500 : false;
    },
    staleTime: 1500,
    placeholderData: keepPreviousData,
  });

  const recentRunsQuery = useQuery({
    queryKey: queryKeys.recentRuns(activeVaultId),
    queryFn: () => getRuns(activeVaultSelector, false, 12),
    enabled: configQuery.isSuccess && Boolean(vaultPath) && needsRecentRuns,
    staleTime: 20_000,
    placeholderData: keepPreviousData,
  });

  const graphQuery = useQuery({
    queryKey: queryKeys.graph(activeVaultId),
    queryFn: () => getGraph(vaultPath),
    enabled: configQuery.isSuccess && activeView === "graph",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const pagesQuery = useQuery({
    queryKey: queryKeys.pages(activeVaultId),
    queryFn: () => getPages(activeVaultSelector),
    enabled: configQuery.isSuccess && activeView === "wiki",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const queryTrendQuery = useQuery({
    queryKey: queryKeys.queryTrends(activeVaultId),
    queryFn: () => getQueryTrends(activeVaultSelector),
    enabled: configQuery.isSuccess && activeView === "query",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const vaultOverviewQueries = useQueries({
    queries: concreteOptions.map((vault) => ({
      queryKey: queryKeys.overview(vault.id),
      queryFn: () => fetchVaultOverview(vault, effectiveConfigPath),
      enabled: configQuery.isSuccess && concreteOptions.length > 1 && needsVaultOverview,
      staleTime: 20_000,
      placeholderData: keepPreviousData,
    })),
  });

  const doctorReport = doctorQuery.data || null;
  const status = statusQuery.data || null;
  const graph = graphQuery.data || null;
  const pages = pagesQuery.data?.pages || [];
  const reports = reportsQuery.data?.reports || [];
  const queryTrend = queryTrendQuery.data || null;
  const activeRuns = activeRunsQuery.data?.runs || [];
  const recentRuns = recentRunsQuery.data?.runs || [];
  const modelProviders = modelProvidersQuery.data || null;
  const vaultOverviews = vaultOptions.length > 1
    ? concreteOptions.map((vault, index) => {
      const query = vaultOverviewQueries[index];
      return query?.data || {
        vault,
        status: vault.id === activeVaultId ? status : null,
        activeRuns: vault.id === activeVaultId ? activeRuns : [],
        recentRuns: vault.id === activeVaultId ? recentRuns : [],
        reports: vault.id === activeVaultId ? reports : [],
        error: query?.error instanceof Error ? query.error.message : query?.isError ? t("vaultRefreshFailed") : null,
      };
    })
    : [{
      vault: activeConcreteVault,
      status,
      activeRuns,
      recentRuns,
      reports,
      error: null,
    }];

  const setLanguage = useCallback((next: Language) => {
    localStorage.setItem("knoarbor.language", next);
    setLanguageState(next);
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((current) => {
      const next = !current;
      localStorage.setItem("knoarbor.sidebarCollapsed", String(next));
      return next;
    });
  }, []);

  const setActiveVaultId = useCallback((next: string) => {
    localStorage.setItem("knoarbor.activeVaultId", next);
    localStorage.setItem("knoarbor.activeVaultId.userSet", "true");
    setSelectedVaultId(next);
    setFocusedPageId(null);
    setFocusedWikiPath(null);
    setFocusedReportPath(null);
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

  const loadVaultState = useCallback(async (vault: VaultOption = activeConcreteVault, scope: VaultRefreshScope = {}) => {
    const normalizedScope = {
      status: scope.status ?? true,
      reports: scope.reports ?? true,
      activeRuns: scope.activeRuns ?? true,
      recentRuns: scope.recentRuns ?? true,
    };
    const tasks: Promise<unknown>[] = [];
    if (normalizedScope.status) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.status(vault.id), queryFn: () => getStatus(vault.path), staleTime: 0 }));
    const selector = buildVaultSelector(effectiveConfigPath, vault);
    if (normalizedScope.reports) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.reports(vault.id), queryFn: () => getReports(selector), staleTime: 0 }));
    if (normalizedScope.activeRuns) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.activeRuns(vault.id), queryFn: () => getActiveRuns(selector), staleTime: 0 }));
    if (normalizedScope.recentRuns) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.recentRuns(vault.id), queryFn: () => getRuns(selector, false, 12), staleTime: 0 }));
    const results = await Promise.allSettled(tasks);
    const failure = results.find((result) => result.status === "rejected");
    if (failure?.status === "rejected") {
      const reason = failure.reason || t("vaultRefreshFailed");
      setNotice({ message: reason instanceof Error ? reason.message : String(reason), error: true });
    }
  }, [activeConcreteVault, effectiveConfigPath, queryClient, t]);

  useEffect(() => {
    const preloadCommonRoutes = () => {
      for (const view of ["runs", "sources", "ingest", "lint", "query", "settings"] satisfies ViewName[]) {
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
  }, [effectiveSummary.vault_id, selectedVaultId, vaultOptions]);

  useEffect(() => {
    const previousRuns = previousActiveRunCountRef.current;
    previousActiveRunCountRef.current = activeRuns.length;
    if (previousRuns > 0 && activeRuns.length === 0) void loadVaultState();
  }, [activeRuns.length, loadVaultState]);

  const refreshAll = useCallback(async () => {
    setNotice(null);
    try {
      const configResult = await queryClient.fetchQuery({ queryKey: queryKeys.config, queryFn: getConfig });
      const nextRegistry = await queryClient.fetchQuery({ queryKey: queryKeys.vaults(configResult.config_path), queryFn: () => getVaults(configResult.config_path) });
      const nextVaultOptions = buildVaultOptions(configResult.summary || {}, nextRegistry);
      const nextVault = resolveConcreteVault(nextVaultOptions, selectedVaultId, configResult.summary || {});
      const nextSelector = buildVaultSelector(configResult.config_path, nextVault);
      const refreshTasks: Promise<unknown>[] = [
        queryClient.fetchQuery({ queryKey: queryKeys.health, queryFn: getHealth, staleTime: 0 }),
      ];
      if (activeView === "overview") {
        refreshTasks.push(queryClient.fetchQuery({
          queryKey: queryKeys.doctor(configResult.config_path),
          queryFn: () => getDoctor(configResult.config_path, { checkModelRuntime: false, checkConnectorRuntime: false }),
          staleTime: 0,
        }));
      }
      if (needsVaultStatus || needsReports || needsRecentRuns || shouldPollRuns) {
        refreshTasks.push(loadVaultState(nextVault, {
          status: needsVaultStatus,
          reports: needsReports,
          activeRuns: shouldPollRuns,
          recentRuns: needsRecentRuns,
        }));
      }
      if (activeView === "graph") {
        refreshTasks.push(queryClient.fetchQuery({ queryKey: queryKeys.graph(nextVault.id), queryFn: () => getGraph(nextVault.path), staleTime: 0 }));
      }
      if (activeView === "wiki") {
        refreshTasks.push(queryClient.fetchQuery({ queryKey: queryKeys.pages(nextVault.id), queryFn: () => getPages(nextSelector), staleTime: 0 }));
      }
      if (activeView === "query") {
        refreshTasks.push(queryClient.fetchQuery({ queryKey: queryKeys.queryTrends(nextVault.id), queryFn: () => getQueryTrends(nextSelector), staleTime: 0 }));
      }
      if (activeView === "chat" || activeView === "settings") {
        refreshTasks.push(queryClient.fetchQuery({ queryKey: queryKeys.modelProviders(configResult.config_path), queryFn: () => getModelProviders(configResult.config_path), staleTime: 0 }));
      }
      await Promise.all(refreshTasks);
      return true;
    } catch (error) {
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      return false;
    }
  }, [activeView, loadVaultState, needsRecentRuns, needsReports, needsVaultStatus, queryClient, selectedVaultId, shouldPollRuns]);

  const refreshManually = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const ok = await refreshAll();
      if (ok) setNotice({ message: t("refreshComplete") });
    } finally {
      setIsRefreshing(false);
    }
  }, [refreshAll, t]);

  useEffect(() => {
    const desktop = window.knoarborDesktop;
    if (!desktop) return undefined;
    return desktop.onCommand((command) => {
      if (command === "settings.open") {
        setWorkspaceSettingsOpen(true);
        return;
      }
      if (command === "chat.new") {
        setPendingChatPrompt("");
        setFocusedPageId(null);
        setFocusedReportPath(null);
        setFocusedWikiPath(null);
        setActiveView("chat");
        return;
      }
      if (command === "docs.open") {
        void desktop.openApiDocs();
        return;
      }
      if (command === "service.restart") {
        setNotice({ message: t("serviceRestarting") });
        void desktop.restartService().then(() => refreshAll());
        return;
      }
      if (command === "logs.open") {
        void desktop.openLogs();
      }
    });
  }, [refreshAll, t]);

  const openPageInGraph = useCallback((pageId: string) => {
    setFocusedPageId(pageId);
    setActiveView("graph");
  }, []);

  const openReport = useCallback((path: string) => {
    setFocusedReportPath(path);
    setActiveView("reports");
  }, []);

  const openWikiPage = useCallback((path: string) => {
    setFocusedWikiPath(path);
    setActiveView("wiki");
  }, []);

  const openWikiPageInVault = useCallback((vaultId: string | null | undefined, path: string) => {
    if (vaultId && vaultId !== activeVaultId) {
      localStorage.setItem("knoarbor.activeVaultId", vaultId);
      localStorage.setItem("knoarbor.activeVaultId.userSet", "true");
      setSelectedVaultId(vaultId);
    }
    setFocusedPageId(null);
    setFocusedReportPath(null);
    setFocusedWikiPath(path);
    setActiveView("wiki");
  }, [activeVaultId]);

  const openChatWithPrompt = useCallback((prompt: string, vaultId?: string | null) => {
    if (vaultId && vaultId !== activeVaultId) {
      localStorage.setItem("knoarbor.activeVaultId", vaultId);
      localStorage.setItem("knoarbor.activeVaultId.userSet", "true");
      setSelectedVaultId(vaultId);
    }
    setFocusedPageId(null);
    setFocusedReportPath(null);
    setFocusedWikiPath(null);
    setPendingChatPrompt(prompt);
    setActiveView("chat");
  }, [activeVaultId]);

  const clearPendingChatPrompt = useCallback(() => {
    setPendingChatPrompt("");
  }, []);

  const openChatSession = useCallback((sessionId: string | null, vaultId?: string | null) => {
    if (vaultId && vaultId !== activeVaultId) {
      localStorage.setItem("knoarbor.activeVaultId", vaultId);
      localStorage.setItem("knoarbor.activeVaultId.userSet", "true");
      setSelectedVaultId(vaultId);
    }
    setFocusedPageId(null);
    setFocusedReportPath(null);
    setFocusedWikiPath(null);
    setPendingChatSessionRequest({ sessionId, vaultId: vaultId || null, requestId: Date.now() });
    setActiveView("chat");
  }, [activeVaultId]);

  const clearPendingChatSessionRequest = useCallback(() => {
    setPendingChatSessionRequest(null);
  }, []);

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
    if (view === "runs") void queryClient.prefetchQuery({ queryKey: queryKeys.recentRuns(activeVaultId), queryFn: () => getRuns(activeVaultSelector, false, 12), staleTime: 20_000 });
  }, [activeVaultId, activeVaultSelector, queryClient, vaultPath]);

  const context: AppContext = useMemo(
    () => ({
      configPath,
      configContent,
      configExists,
      doctorReport,
      graph,
      focusedPageId,
      focusedWikiPath,
      pendingChatPrompt,
      pendingChatSessionRequest,
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
      openPageInGraph,
      openWikiPage,
      openWikiPageInVault,
      openChatWithPrompt,
      clearPendingChatPrompt,
      openChatSession,
      clearPendingChatSessionRequest,
      openReport,
      openSettings: () => setWorkspaceSettingsOpen(true),
      status,
      summary: effectiveSummary,
      activeVaultId,
      activeVaultSelector,
      vaultOptions,
      vaultOverviews,
      setActiveVaultId,
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
      focusedPageId,
      pendingChatPrompt,
      pendingChatSessionRequest,
      focusedReportPath,
      focusedWikiPath,
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
      setActiveRunsCached,
      status,
      effectiveSummary,
      activeVaultId,
      activeVaultSelector,
      vaultOptions,
      vaultOverviews,
      setActiveVaultId,
      vaultPath,
      refreshAll,
      loadVaultState,
      language,
      setLanguage,
      openPageInGraph,
      openWikiPage,
      openWikiPageInVault,
      openChatWithPrompt,
      clearPendingChatPrompt,
      openChatSession,
      clearPendingChatSessionRequest,
      openReport,
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

  return (
    <AppShell
      activeView={activeView}
      language={language}
      serviceOnline={serviceOnline}
      sidebarCollapsed={sidebarCollapsed}
      t={t}
      onChangeView={setActiveView}
      onPreloadView={preloadView}
      onSetLanguage={setLanguage}
      onToggleSidebar={toggleSidebar}
      onOpenWorkspaceSettings={() => setWorkspaceSettingsOpen(true)}
      onOpenApiDocs={window.knoarborDesktop ? () => void window.knoarborDesktop?.openApiDocs() : undefined}
      sidebarSlot={<SidebarRecentSessions context={context} />}
    >
        <RouteErrorBoundary
          key={activeView}
          fallbackTitle={t("routeLoadFailed")}
          fallbackCopy={t("routeLoadFailedCopy")}
          reloadLabel={t("reloadPage")}
        >
          <Suspense fallback={<section className="panel page-loading"><LoadingBlock title={t("pageLoading")} copy={t("pageLoadingCopy")} /></section>}>
            {activeView === "chat" && <ChatPage context={context} />}
            {activeView === "overview" && <OverviewPage context={context} onNavigate={setActiveView} />}
            {activeView === "runs" && <RunsPage context={context} />}
            {activeView === "sources" && <SourcesPage context={context} />}
            {activeView === "wiki" && <WikiPage context={context} focusedPagePath={focusedWikiPath} />}
            {activeView === "ingest" && <IngestPage context={context} />}
            {activeView === "lint" && <LintPage context={context} />}
            {activeView === "query" && <QueryPage context={context} />}
            {activeView === "graph" && <GraphPage graph={context.graph} context={context} />}
            {activeView === "reports" && <ReportsPage context={context} focusedReportPath={focusedReportPath} />}
            {activeView === "tokens" && <TokensPage context={context} />}
            {activeView === "settings" && <ConfigPage context={context} />}
            {activeView === "docs" && <DocsPage context={context} />}
          </Suspense>
        </RouteErrorBoundary>
        <WorkspaceSettingsModal isOpen={workspaceSettingsOpen} t={t} onClose={() => setWorkspaceSettingsOpen(false)}>
          <Suspense fallback={<section className="panel page-loading"><LoadingBlock title={t("pageLoading")} copy={t("pageLoadingCopy")} /></section>}>
            <ConfigPage context={context} embedded />
          </Suspense>
        </WorkspaceSettingsModal>
    </AppShell>
  );
}

export type AppContext = {
  configPath: string | null;
  configContent: string;
  configExists: boolean;
  doctorReport: DoctorReport | null;
  graph: GraphResponse | null;
  focusedPageId: string | null;
  focusedWikiPath: string | null;
  pendingChatPrompt: string;
  pendingChatSessionRequest: PendingChatSessionRequest | null;
  healthHint: string;
  pages: PageSummary[];
  queryResults: QueryResult[];
  queryContextPack: string;
  queryTrend: QueryTrendResponse | null;
  activeRuns: RunRecord[];
  recentRuns: RunRecord[];
  reports: ReportSummary[];
  serviceOnline: boolean | null;
  modelProviders: ModelProvidersResponse | null;
  modelProbeResults: Record<string, ModelProviderProbeState>;
  selectedChatProvider: string;
  setModelProbeResults: Dispatch<SetStateAction<Record<string, ModelProviderProbeState>>>;
  setSelectedChatProvider: (provider: string) => void;
  setConfigContent: Dispatch<SetStateAction<string>>;
  setConfigPath: Dispatch<SetStateAction<string | null>>;
  setConfigExists: Dispatch<SetStateAction<boolean>>;
  setDoctorReport: Dispatch<SetStateAction<DoctorReport | null>>;
  setNotice: Dispatch<SetStateAction<AppNotice | null>>;
  setQueryResults: Dispatch<SetStateAction<QueryResult[]>>;
  setQueryContextPack: Dispatch<SetStateAction<string>>;
  setQueryTrend: Dispatch<SetStateAction<QueryTrendResponse | null>>;
  setActiveRuns: Dispatch<SetStateAction<RunRecord[]>>;
  setRecentRuns: Dispatch<SetStateAction<RunRecord[]>>;
  setSummary: Dispatch<SetStateAction<ConfigSummary>>;
  setStatus: Dispatch<SetStateAction<UiStatusResponse | null>>;
  setGraph: Dispatch<SetStateAction<GraphResponse | null>>;
  setPages: Dispatch<SetStateAction<PageSummary[]>>;
  setReports: Dispatch<SetStateAction<ReportSummary[]>>;
  navigate: (view: ViewName) => void;
  openPageInGraph: (pageId: string) => void;
  openWikiPage: (path: string) => void;
  openWikiPageInVault: (vaultId: string | null | undefined, path: string) => void;
  openChatWithPrompt: (prompt: string, vaultId?: string | null) => void;
  clearPendingChatPrompt: () => void;
  openChatSession: (sessionId: string | null, vaultId?: string | null) => void;
  clearPendingChatSessionRequest: () => void;
  openReport: (path: string) => void;
  openSettings: () => void;
  status: UiStatusResponse | null;
  summary: ConfigSummary;
  activeVaultId: string;
  activeVaultSelector: VaultSelector;
  vaultOptions: VaultOption[];
  vaultOverviews: VaultOverview[];
  setActiveVaultId: (vaultId: string) => void;
  vaultPath: string;
  refreshAll: () => Promise<boolean>;
  loadVaultState: (vault?: VaultOption, scope?: VaultRefreshScope) => Promise<void>;
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
};

export type PendingChatSessionRequest = {
  sessionId: string | null;
  vaultId?: string | null;
  requestId: number;
};

export type VaultRefreshScope = {
  status?: boolean;
  reports?: boolean;
  activeRuns?: boolean;
  recentRuns?: boolean;
};

async function fetchVaultOverview(vault: VaultOption, configPath: string | null): Promise<VaultOverview> {
  const selector = buildVaultSelector(configPath, vault);
  const [statusResult, activeRunsResult, recentRunsResult, reportsResult] = await Promise.allSettled([
    getStatus(vault.path),
    getActiveRuns(selector),
    getRuns(selector, false, 6),
    getReports(selector),
  ]);
  const error = [statusResult, activeRunsResult, recentRunsResult, reportsResult]
    .find((result) => result.status === "rejected");
  return {
    vault,
    status: statusResult.status === "fulfilled" ? statusResult.value : null,
    activeRuns: activeRunsResult.status === "fulfilled" ? activeRunsResult.value.runs : [],
    recentRuns: recentRunsResult.status === "fulfilled" ? recentRunsResult.value.runs : [],
    reports: reportsResult.status === "fulfilled" ? reportsResult.value.reports : [],
    error: error?.status === "rejected" ? String(error.reason instanceof Error ? error.reason.message : error.reason) : null,
  };
}

function readStoredModelProbeResults(): Record<string, ModelProviderProbeState> {
  try {
    const raw = localStorage.getItem("knoarbor.modelProbeResults");
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}
