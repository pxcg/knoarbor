import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";

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
import { detectLanguage, translate } from "./i18n";
import { ConfigPage } from "./pages/ConfigPage";
import { DocsPage } from "./pages/DocsPage";
import { GraphPage } from "./pages/GraphPage";
import { IngestPage } from "./pages/IngestPage";
import { LintPage } from "./pages/LintPage";
import { OverviewPage } from "./pages/OverviewPage";
import { QueryPage } from "./pages/QueryPage";
import { ReportsPage } from "./pages/ReportsPage";
import { RunsPage } from "./pages/RunsPage";
import { SourcesPage } from "./pages/SourcesPage";
import { WikiPage } from "./pages/WikiPage";
import type { Language, ViewName } from "./types";
import type { RunRecord } from "./types";

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
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [notice, setNotice] = useState<AppNotice | null>(null);
  const [queryResults, setQueryResults] = useState<QueryResult[]>([]);
  const [queryContextPack, setQueryContextPack] = useState("");
  const [queryTrend, setQueryTrend] = useState<QueryTrendResponse | null>(null);
  const [activeRuns, setActiveRuns] = useState<RunRecord[]>([]);
  const [recentRuns, setRecentRuns] = useState<RunRecord[]>([]);
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

  const loadVaultState = useCallback(async (path: string) => {
    const [statusResult, graphResult, pagesResult, reportsResult, activeRunsResult, recentRunsResult, queryTrendResult] = await Promise.allSettled([
      getStatus(path),
      getGraph(path),
      getPages(path),
      getReports(path),
      getActiveRuns(path),
      getRuns(path, false),
      getQueryTrends(path),
    ]);
    if (statusResult.status === "fulfilled") setStatus(statusResult.value);
    if (graphResult.status === "fulfilled") setGraph(graphResult.value);
    if (pagesResult.status === "fulfilled") setPages(pagesResult.value.pages || []);
    if (reportsResult.status === "fulfilled") setReports(reportsResult.value.reports || []);
    if (activeRunsResult.status === "fulfilled") setActiveRuns(activeRunsResult.value.runs || []);
    if (recentRunsResult.status === "fulfilled") setRecentRuns(recentRunsResult.value.runs || []);
    if (queryTrendResult.status === "fulfilled") setQueryTrend(queryTrendResult.value);
    if (statusResult.status === "rejected" || graphResult.status === "rejected" || pagesResult.status === "rejected" || reportsResult.status === "rejected") {
      const reason =
        statusResult.status === "rejected"
          ? statusResult.reason
          : graphResult.status === "rejected"
            ? graphResult.reason
            : pagesResult.status === "rejected"
              ? pagesResult.reason
              : reportsResult.status === "rejected"
                ? reportsResult.reason
                : t("vaultRefreshFailed");
      setNotice({ message: reason instanceof Error ? reason.message : String(reason), error: true });
    }
  }, [t]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void getActiveRuns(vaultPath)
        .then((response) => {
          const nextRuns = response.runs || [];
          setActiveRuns((currentRuns) => {
            if (currentRuns.length > 0 && nextRuns.length === 0) {
              void loadVaultState(vaultPath);
            }
            return nextRuns;
          });
        })
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [loadVaultState, vaultPath]);

  const refreshAll = useCallback(async () => {
    setNotice(null);
    await loadHealth();
    try {
      const config = await loadConfig();
      const path = config.summary?.vault_path || "./wiki";
      const [doctorResult] = await Promise.allSettled([getDoctor(config.config_path), loadVaultState(path)]);
      if (doctorResult.status === "fulfilled") {
        setDoctorReport(doctorResult.value);
      } else {
        setDoctorReport(null);
      }
      return true;
    } catch (error) {
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      return false;
    }
  }, [loadConfig, loadHealth, loadVaultState]);

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

        {activeView === "overview" && <OverviewPage context={context} onNavigate={setActiveView} />}
        {activeView === "runs" && <RunsPage context={context} />}
        {activeView === "sources" && <SourcesPage context={context} />}
        {activeView === "wiki" && <WikiPage context={context} focusedPagePath={focusedWikiPath} />}
        {activeView === "ingest" && <IngestPage context={context} />}
        {activeView === "lint" && <LintPage context={context} />}
        {activeView === "query" && <QueryPage context={context} />}
        {activeView === "graph" && <GraphPage graph={context.graph} context={context} />}
        {activeView === "reports" && <ReportsPage context={context} focusedReportPath={focusedReportPath} />}
        {activeView === "settings" && <ConfigPage context={context} />}
        {activeView === "docs" && <DocsPage context={context} />}
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
