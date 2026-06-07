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
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getConfig,
  getDoctor,
  getPages,
  getGraph,
  getHealth,
  getQueryTrends,
  getActiveRuns,
  getRuns,
  getReports,
  getStatus,
  type ConfigSummary,
  type DoctorReport,
  type GraphResponse,
  type PageSummary,
  type QueryTrendResponse,
  type QueryResult,
  type ReportSummary,
  type UiStatusResponse,
} from "./api/client";
import { AppShell } from "./components/AppShell";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { detectLanguage, translate } from "./i18n";
import { queryKeys } from "./queryKeys";
import type { Language, ViewName } from "./types";
import type { RunRecord } from "./types";

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
  const [activeView, setActiveView] = useState<ViewName>("overview");
  const [language, setLanguageState] = useState<Language>(() => detectLanguage());
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [healthHint, setHealthHint] = useState(() => translate(detectLanguage(), "healthCheck"));
  const [configPath, setConfigPath] = useState<string | null>(null);
  const [configContent, setConfigContent] = useState("");
  const [configExists, setConfigExists] = useState(false);
  const [summary, setSummary] = useState<ConfigSummary>({});
  const [notice, setNotice] = useState<AppNotice | null>(null);
  const [queryResults, setQueryResults] = useState<QueryResult[]>([]);
  const [queryContextPack, setQueryContextPack] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [focusedPageId, setFocusedPageId] = useState<string | null>(null);
  const [focusedWikiPath, setFocusedWikiPath] = useState<string | null>(null);
  const [focusedReportPath, setFocusedReportPath] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("knoarbor.sidebarCollapsed") === "true");
  const [selectedVaultId, setSelectedVaultId] = useState(() => localStorage.getItem("knoarbor.activeVaultId") || "");
  const previousActiveRunCountRef = useRef(0);
  const queryClient = useQueryClient();

  const t = useCallback((key: string) => translate(language, key), [language]);
  const shouldPollRuns = activeView === "overview" || activeView === "runs" || activeView === "ingest" || activeView === "lint";

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
  const vaultOptions = useMemo(() => buildVaultOptions(effectiveSummary), [effectiveSummary]);
  const activeVault =
    vaultOptions.find((vault) => vault.id === selectedVaultId) ||
    vaultOptions.find((vault) => vault.id === effectiveSummary.vault_id) ||
    vaultOptions[0];
  const vaultPath = activeVault?.path || effectiveSummary.vault_path || "./wiki";
  const activeVaultId = activeVault?.id || effectiveSummary.vault_id || "default";

  const doctorQuery = useQuery({
    queryKey: queryKeys.doctor(effectiveConfigPath),
    queryFn: () => getDoctor(effectiveConfigPath, { checkModelRuntime: false, checkConnectorRuntime: false }),
    enabled: configQuery.isSuccess,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const statusQuery = useQuery({
    queryKey: queryKeys.status(vaultPath),
    queryFn: () => getStatus(vaultPath),
    enabled: configQuery.isSuccess && Boolean(vaultPath),
    staleTime: 20_000,
    placeholderData: keepPreviousData,
  });

  const reportsQuery = useQuery({
    queryKey: queryKeys.reports(vaultPath),
    queryFn: () => getReports(vaultPath),
    enabled: configQuery.isSuccess && Boolean(vaultPath),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const activeRunsQuery = useQuery({
    queryKey: queryKeys.activeRuns(vaultPath),
    queryFn: () => getActiveRuns(vaultPath),
    enabled: configQuery.isSuccess && Boolean(vaultPath),
    refetchInterval: (query) => {
      const runs = query.state.data?.runs || [];
      return shouldPollRuns || runs.length > 0 ? 2500 : false;
    },
    staleTime: 1500,
    placeholderData: keepPreviousData,
  });

  const recentRunsQuery = useQuery({
    queryKey: queryKeys.recentRuns(vaultPath),
    queryFn: () => getRuns(vaultPath, false, 12),
    enabled: configQuery.isSuccess && (activeView === "runs" || activeView === "overview"),
    staleTime: 20_000,
    placeholderData: keepPreviousData,
  });

  const graphQuery = useQuery({
    queryKey: queryKeys.graph(vaultPath),
    queryFn: () => getGraph(vaultPath),
    enabled: configQuery.isSuccess && activeView === "graph",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const pagesQuery = useQuery({
    queryKey: queryKeys.pages(vaultPath),
    queryFn: () => getPages(vaultPath),
    enabled: configQuery.isSuccess && activeView === "wiki",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const queryTrendQuery = useQuery({
    queryKey: queryKeys.queryTrends(vaultPath),
    queryFn: () => getQueryTrends(vaultPath),
    enabled: configQuery.isSuccess && activeView === "query",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const doctorReport = doctorQuery.data || null;
  const status = statusQuery.data || null;
  const graph = graphQuery.data || null;
  const pages = pagesQuery.data?.pages || [];
  const reports = reportsQuery.data?.reports || [];
  const queryTrend = queryTrendQuery.data || null;
  const activeRuns = activeRunsQuery.data?.runs || [];
  const recentRuns = recentRunsQuery.data?.runs || [];

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
    setSelectedVaultId(next);
    setFocusedPageId(null);
    setFocusedWikiPath(null);
    setFocusedReportPath(null);
  }, []);

  const loadVaultState = useCallback(async (path: string) => {
    const [statusResult, reportsResult, activeRunsResult, recentRunsResult] = await Promise.allSettled([
      queryClient.refetchQueries({ queryKey: queryKeys.status(path) }),
      queryClient.refetchQueries({ queryKey: queryKeys.reports(path) }),
      queryClient.refetchQueries({ queryKey: queryKeys.activeRuns(path) }),
      queryClient.refetchQueries({ queryKey: queryKeys.recentRuns(path) }),
    ]);
    if (statusResult.status === "rejected" || reportsResult.status === "rejected" || activeRunsResult.status === "rejected" || recentRunsResult.status === "rejected") {
      const reason =
        statusResult.status === "rejected"
          ? statusResult.reason
          : reportsResult.status === "rejected"
            ? reportsResult.reason
            : activeRunsResult.status === "rejected"
              ? activeRunsResult.reason
              : recentRunsResult.status === "rejected"
                ? recentRunsResult.reason
                : t("vaultRefreshFailed");
      setNotice({ message: reason instanceof Error ? reason.message : String(reason), error: true });
    }
  }, [queryClient, t]);

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
    const exists = vaultOptions.some((vault) => vault.id === selectedVaultId);
    if (exists) return;
    const next = effectiveSummary.vault_id || vaultOptions[0].id;
    localStorage.setItem("knoarbor.activeVaultId", next);
    setSelectedVaultId(next);
  }, [effectiveSummary.vault_id, selectedVaultId, vaultOptions]);

  useEffect(() => {
    const previousRuns = previousActiveRunCountRef.current;
    previousActiveRunCountRef.current = activeRuns.length;
    if (previousRuns > 0 && activeRuns.length === 0) void loadVaultState(vaultPath);
  }, [activeRuns.length, loadVaultState, vaultPath]);

  const refreshAll = useCallback(async () => {
    setNotice(null);
    try {
      const configResult = await queryClient.fetchQuery({ queryKey: queryKeys.config, queryFn: getConfig });
      const nextVaultOptions = buildVaultOptions(configResult.summary || {});
      const nextVault =
        nextVaultOptions.find((vault) => vault.id === selectedVaultId) ||
        nextVaultOptions.find((vault) => vault.id === configResult.summary?.vault_id) ||
        nextVaultOptions[0];
      const path = nextVault?.path || configResult.summary?.vault_path || "./wiki";
      await Promise.all([
        queryClient.refetchQueries({ queryKey: queryKeys.health }),
        queryClient.refetchQueries({ queryKey: queryKeys.doctor(configResult.config_path) }),
        loadVaultState(path),
      ]);
      return true;
    } catch (error) {
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      return false;
    }
  }, [loadVaultState, queryClient, selectedVaultId]);

  const refreshManually = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const ok = await refreshAll();
      if (ok) setNotice({ message: t("refreshComplete") });
    } finally {
      setIsRefreshing(false);
    }
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

  const setDoctorReportCached: Dispatch<SetStateAction<DoctorReport | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.doctor(configPath), (current: DoctorReport | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [configPath, queryClient]);

  const setStatusCached: Dispatch<SetStateAction<UiStatusResponse | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.status(vaultPath), (current: UiStatusResponse | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [queryClient, vaultPath]);

  const setGraphCached: Dispatch<SetStateAction<GraphResponse | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.graph(vaultPath), (current: GraphResponse | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [queryClient, vaultPath]);

  const setPagesCached: Dispatch<SetStateAction<PageSummary[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.pages(vaultPath), (current: { vault_path: string; pages: PageSummary[] } | undefined) => {
      const pagesValue = typeof value === "function" ? value(current?.pages || []) : value;
      return { vault_path: vaultPath, pages: pagesValue };
    });
  }, [queryClient, vaultPath]);

  const setReportsCached: Dispatch<SetStateAction<ReportSummary[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.reports(vaultPath), (current: { vault_path: string; reports: ReportSummary[] } | undefined) => {
      const reportsValue = typeof value === "function" ? value(current?.reports || []) : value;
      return { vault_path: vaultPath, reports: reportsValue };
    });
  }, [queryClient, vaultPath]);

  const setQueryTrendCached: Dispatch<SetStateAction<QueryTrendResponse | null>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.queryTrends(vaultPath), (current: QueryTrendResponse | null | undefined) =>
      typeof value === "function" ? value(current || null) : value,
    );
  }, [queryClient, vaultPath]);

  const setActiveRunsCached: Dispatch<SetStateAction<RunRecord[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.activeRuns(vaultPath), (current: { runs: RunRecord[] } | undefined) => {
      const runsValue = typeof value === "function" ? value(current?.runs || []) : value;
      return { runs: runsValue };
    });
  }, [queryClient, vaultPath]);

  const setRecentRunsCached: Dispatch<SetStateAction<RunRecord[]>> = useCallback((value) => {
    queryClient.setQueryData(queryKeys.recentRuns(vaultPath), (current: { runs: RunRecord[] } | undefined) => {
      const runsValue = typeof value === "function" ? value(current?.runs || []) : value;
      return { runs: runsValue };
    });
  }, [queryClient, vaultPath]);

  const preloadView = useCallback((view: ViewName) => {
    preloadRoute(view);
    if (view === "graph") void queryClient.prefetchQuery({ queryKey: queryKeys.graph(vaultPath), queryFn: () => getGraph(vaultPath), staleTime: 60_000 });
    if (view === "wiki") void queryClient.prefetchQuery({ queryKey: queryKeys.pages(vaultPath), queryFn: () => getPages(vaultPath), staleTime: 60_000 });
    if (view === "query") void queryClient.prefetchQuery({ queryKey: queryKeys.queryTrends(vaultPath), queryFn: () => getQueryTrends(vaultPath), staleTime: 60_000 });
    if (view === "runs") void queryClient.prefetchQuery({ queryKey: queryKeys.recentRuns(vaultPath), queryFn: () => getRuns(vaultPath, false, 12), staleTime: 20_000 });
  }, [queryClient, vaultPath]);

  const context: AppContext = useMemo(
    () => ({
      configPath,
      configContent,
      configExists,
      doctorReport,
      graph,
      focusedPageId,
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
      openReport,
      status,
      summary: effectiveSummary,
      activeVaultId,
      vaultOptions,
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
      setActiveRunsCached,
      status,
      effectiveSummary,
      activeVaultId,
      vaultOptions,
      setActiveVaultId,
      vaultPath,
      refreshAll,
      loadVaultState,
      language,
      setLanguage,
      openPageInGraph,
      openWikiPage,
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
      isRefreshing={isRefreshing}
      language={language}
      serviceOnline={serviceOnline}
      sidebarCollapsed={sidebarCollapsed}
      t={t}
      onChangeView={setActiveView}
      onPreloadView={preloadView}
      onRefresh={refreshManually}
      onSetLanguage={setLanguage}
      onToggleSidebar={toggleSidebar}
      vaultOptions={vaultOptions}
      activeVaultId={activeVaultId}
      onSetActiveVault={setActiveVaultId}
    >
        {notice && (
          <section className={`notice ${notice.error ? "error" : ""}`}>
            <span>{notice.message}</span>
            {notice.actionLabel && notice.onAction && (
              <button className="button secondary small-button" type="button" onClick={notice.onAction}>
                {notice.actionLabel}
              </button>
            )}
          </section>
        )}

        <RouteErrorBoundary
          key={activeView}
          fallbackTitle={t("routeLoadFailed")}
          fallbackCopy={t("routeLoadFailedCopy")}
          reloadLabel={t("reloadPage")}
        >
          <Suspense fallback={<section className="panel page-loading">{t("loading")}</section>}>
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
  healthHint: string;
  pages: PageSummary[];
  queryResults: QueryResult[];
  queryContextPack: string;
  queryTrend: QueryTrendResponse | null;
  activeRuns: RunRecord[];
  recentRuns: RunRecord[];
  reports: ReportSummary[];
  serviceOnline: boolean | null;
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
  openReport: (path: string) => void;
  status: UiStatusResponse | null;
  summary: ConfigSummary;
  activeVaultId: string;
  vaultOptions: Array<{ id: string; name: string; path: string }>;
  setActiveVaultId: (vaultId: string) => void;
  vaultPath: string;
  refreshAll: () => Promise<boolean>;
  loadVaultState: (path: string) => Promise<void>;
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
};

function buildVaultOptions(summary: ConfigSummary): Array<{ id: string; name: string; path: string }> {
  const configured = summary.vaults?.filter((vault) => vault.id && vault.path) || [];
  if (configured.length) {
    return configured.map((vault) => ({
      id: vault.id,
      name: vault.name || vault.id,
      path: vault.path,
    }));
  }
  return [
    {
      id: summary.vault_id || "default",
      name: summary.vault_name || summary.project_name || "KnoArbor",
      path: summary.vault_path || "./wiki",
    },
  ];
}
