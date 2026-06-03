import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

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
  const [doctorReport, setDoctorReport] = useState<DoctorReport | null>(null);
  const [status, setStatus] = useState<UiStatusResponse | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [graphLoadedFor, setGraphLoadedFor] = useState<string | null>(null);
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [pagesLoadedFor, setPagesLoadedFor] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [notice, setNotice] = useState<AppNotice | null>(null);
  const [queryResults, setQueryResults] = useState<QueryResult[]>([]);
  const [queryContextPack, setQueryContextPack] = useState("");
  const [queryTrend, setQueryTrend] = useState<QueryTrendResponse | null>(null);
  const [queryTrendLoadedFor, setQueryTrendLoadedFor] = useState<string | null>(null);
  const [activeRuns, setActiveRuns] = useState<RunRecord[]>([]);
  const [recentRuns, setRecentRuns] = useState<RunRecord[]>([]);
  const [recentRunsLoadedFor, setRecentRunsLoadedFor] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [focusedPageId, setFocusedPageId] = useState<string | null>(null);
  const [focusedWikiPath, setFocusedWikiPath] = useState<string | null>(null);
  const [focusedReportPath, setFocusedReportPath] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("knoarbor.sidebarCollapsed") === "true");

  const vaultPath = summary.vault_path || "./wiki";
  const t = useCallback((key: string) => translate(language, key), [language]);

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

  const loadHealth = useCallback(async () => {
    try {
      const health = await getHealth();
      setServiceOnline(true);
      setHealthHint(health.status ? t("healthReachable") : t("healthResponded"));
    } catch (error) {
      setServiceOnline(false);
      setHealthHint(error instanceof Error ? error.message : t("healthFailed"));
    }
  }, [t]);

  const loadConfig = useCallback(async () => {
    const config = await getConfig();
    setConfigPath(config.config_path);
    setConfigContent(config.content);
    setConfigExists(config.exists);
    setSummary(config.summary || {});
    return config;
  }, []);

  const loadDoctor = useCallback(async (path: string | null) => {
    try {
      const report = await getDoctor(path, { checkModelRuntime: false, checkConnectorRuntime: false });
      setDoctorReport(report);
    } catch {
      // Doctor is advisory for onboarding and preflight; config/status loading remains authoritative.
      setDoctorReport(null);
    }
  }, []);

  const loadVaultState = useCallback(async (path: string) => {
    setGraphLoadedFor(null);
    setPagesLoadedFor(null);
    setQueryTrendLoadedFor(null);
    setRecentRunsLoadedFor(null);
    setRecentRuns([]);
    const [statusResult, reportsResult, activeRunsResult] = await Promise.allSettled([
      getStatus(path),
      getReports(path),
      getActiveRuns(path),
    ]);
    if (statusResult.status === "fulfilled") setStatus(statusResult.value);
    if (reportsResult.status === "fulfilled") setReports(reportsResult.value.reports || []);
    if (activeRunsResult.status === "fulfilled") setActiveRuns(activeRunsResult.value.runs || []);
    if (statusResult.status === "rejected" || reportsResult.status === "rejected") {
      const reason =
        statusResult.status === "rejected"
          ? statusResult.reason
          : reportsResult.status === "rejected"
            ? reportsResult.reason
            : t("vaultRefreshFailed");
      setNotice({ message: reason instanceof Error ? reason.message : String(reason), error: true });
    }
  }, [t]);

  const loadRecentRunsState = useCallback(async (path: string) => {
    try {
      const response = await getRuns(path, false, 12);
      setRecentRuns(response.runs || []);
      setRecentRunsLoadedFor(path);
    } catch {
      // Recent runs are secondary navigation data; active run polling should not fail because of them.
    }
  }, []);

  const loadGraphState = useCallback(async (path: string) => {
    try {
      const response = await getGraph(path);
      setGraph(response);
      setGraphLoadedFor(path);
    } catch (error) {
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }, []);

  const loadPagesState = useCallback(async (path: string) => {
    try {
      const response = await getPages(path);
      setPages(response.pages || []);
      setPagesLoadedFor(path);
    } catch (error) {
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    }
  }, []);

  const loadQueryTrendState = useCallback(async (path: string) => {
    try {
      const response = await getQueryTrends(path);
      setQueryTrend(response);
      setQueryTrendLoadedFor(path);
    } catch {
      // Query trends are advisory; failing to read them should not block the page.
    }
  }, []);

  useEffect(() => {
    const shouldPollRuns = activeView === "overview" || activeView === "runs" || activeView === "ingest" || activeView === "lint" || activeRuns.length > 0;
    if (!shouldPollRuns) return undefined;
    const timer = window.setInterval(() => {
      void getActiveRuns(vaultPath)
        .then((response) => {
          const nextRuns = response.runs || [];
          setActiveRuns((currentRuns) => {
            if (currentRuns.length > 0 && nextRuns.length === 0) {
              void loadVaultState(vaultPath);
              void loadRecentRunsState(vaultPath);
            }
            return nextRuns;
          });
        })
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [activeRuns.length, activeView, loadRecentRunsState, loadVaultState, vaultPath]);

  useEffect(() => {
    if (activeView === "graph" && graphLoadedFor !== vaultPath) void loadGraphState(vaultPath);
    if (activeView === "wiki" && pagesLoadedFor !== vaultPath) void loadPagesState(vaultPath);
    if (activeView === "query" && queryTrendLoadedFor !== vaultPath) void loadQueryTrendState(vaultPath);
    if (activeView === "runs" && recentRunsLoadedFor !== vaultPath) void loadRecentRunsState(vaultPath);
  }, [activeView, graphLoadedFor, loadGraphState, loadPagesState, loadQueryTrendState, loadRecentRunsState, pagesLoadedFor, queryTrendLoadedFor, recentRunsLoadedFor, vaultPath]);

  useEffect(() => {
    const preloadCommonRoutes = () => {
      for (const view of ["runs", "sources", "ingest", "lint", "query", "settings"] satisfies ViewName[]) {
        preloadRoute(view);
      }
    };
    const timer = window.setTimeout(preloadCommonRoutes, 1200);
    return () => window.clearTimeout(timer);
  }, []);

  const refreshAll = useCallback(async () => {
    setNotice(null);
    await loadHealth();
    try {
      const config = await loadConfig();
      const path = config.summary?.vault_path || "./wiki";
      await Promise.all([loadVaultState(path), loadDoctor(config.config_path)]);
      return true;
    } catch (error) {
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      return false;
    }
  }, [loadConfig, loadDoctor, loadHealth, loadVaultState]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

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

  const preloadView = useCallback((view: ViewName) => {
    preloadRoute(view);
    if (view === "graph" && graphLoadedFor !== vaultPath) void loadGraphState(vaultPath);
    if (view === "wiki" && pagesLoadedFor !== vaultPath) void loadPagesState(vaultPath);
    if (view === "query" && queryTrendLoadedFor !== vaultPath) void loadQueryTrendState(vaultPath);
    if (view === "runs" && recentRunsLoadedFor !== vaultPath) void loadRecentRunsState(vaultPath);
  }, [graphLoadedFor, loadGraphState, loadPagesState, loadQueryTrendState, loadRecentRunsState, pagesLoadedFor, queryTrendLoadedFor, recentRunsLoadedFor, vaultPath]);

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
      setDoctorReport,
      setNotice,
      setQueryResults,
      setQueryContextPack,
      setQueryTrend,
      setActiveRuns,
      setRecentRuns,
      setSummary,
      setStatus,
      setGraph,
      setPages,
      setReports,
      navigate: setActiveView,
      openPageInGraph,
      openWikiPage,
      openReport,
      status,
      summary,
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
      status,
      summary,
      vaultPath,
      refreshAll,
      loadVaultState,
      language,
      setLanguage,
      openPageInGraph,
      openWikiPage,
      openReport,
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
  vaultPath: string;
  refreshAll: () => Promise<boolean>;
  loadVaultState: (path: string) => Promise<void>;
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
};
