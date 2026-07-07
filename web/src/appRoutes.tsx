import { lazy, Suspense } from "react";

import type { AppContext } from "./appContext";
import { LoadingBlock } from "./components/LoadingBlock";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import type { ViewName } from "./types";

const loadChatPage = () => import("./pages/ChatPage").then((module) => ({ default: module.ChatPage }));
const loadOverviewPage = () => import("./pages/OverviewPage").then((module) => ({ default: module.OverviewPage }));
const loadSourcesPage = () => import("./pages/SourcesPage").then((module) => ({ default: module.SourcesPage }));
const loadIngestPage = () => import("./pages/ImportPage").then((module) => ({ default: module.ImportPage }));
const loadLintPage = () => import("./pages/LintPage").then((module) => ({ default: module.LintPage }));
const loadQueryPage = () => import("./pages/QueryPage").then((module) => ({ default: module.QueryPage }));
const loadWikiPage = () => import("./pages/WikiPage").then((module) => ({ default: module.WikiPage }));
const loadGraphPage = () => import("./pages/GraphPage").then((module) => ({ default: module.GraphPage }));
const loadReportsPage = () => import("./pages/ReportsPage").then((module) => ({ default: module.ReportsPage }));
const loadTokensPage = () => import("./pages/TokensPage").then((module) => ({ default: module.TokensPage }));
const loadConfigPage = () => import("./pages/ConfigPage").then((module) => ({ default: module.ConfigPage }));

const routePreloaders = {
  chat: loadChatPage,
  overview: loadOverviewPage,
  sources: loadSourcesPage,
  ingest: loadIngestPage,
  lint: loadLintPage,
  query: loadQueryPage,
  wiki: loadWikiPage,
  graph: loadGraphPage,
  reports: loadReportsPage,
  tokens: loadTokensPage,
  settings: loadConfigPage,
} satisfies Record<ViewName, () => Promise<unknown>>;

const preloadedRoutes = new Set<ViewName>();

export function preloadRoute(view: ViewName) {
  if (preloadedRoutes.has(view)) return;
  preloadedRoutes.add(view);
  void routePreloaders[view]().catch(() => {
    preloadedRoutes.delete(view);
  });
}

const ChatPage = lazy(loadChatPage);
const OverviewPage = lazy(loadOverviewPage);
const SourcesPage = lazy(loadSourcesPage);
const IngestPage = lazy(loadIngestPage);
const LintPage = lazy(loadLintPage);
const QueryPage = lazy(loadQueryPage);
const WikiPage = lazy(loadWikiPage);
const GraphPage = lazy(loadGraphPage);
const ReportsPage = lazy(loadReportsPage);
const TokensPage = lazy(loadTokensPage);
const ConfigPage = lazy(loadConfigPage);

export function AppRoutes({ activeView, context, onNavigate }: { activeView: ViewName; context: AppContext; onNavigate: (view: ViewName) => void }) {
  const t = context.t;
  return (
    <RouteErrorBoundary
      key={activeView}
      fallbackTitle={t("routeLoadFailed")}
      fallbackCopy={t("routeLoadFailedCopy")}
      reloadLabel={t("reloadPage")}
    >
      <Suspense fallback={<section className="panel page-loading"><LoadingBlock title={t("pageLoading")} copy={t("pageLoadingCopy")} /></section>}>
        {activeView === "chat" && <ChatPage context={context} />}
        {activeView === "overview" && <OverviewPage context={context} onNavigate={onNavigate} />}
        {activeView === "sources" && <SourcesPage context={context} />}
        {activeView === "wiki" && <WikiPage context={context} focusedPagePath={context.focusedWikiPath} />}
        {activeView === "ingest" && <IngestPage context={context} />}
        {activeView === "lint" && <LintPage context={context} />}
        {activeView === "query" && <QueryPage context={context} />}
        {activeView === "graph" && <GraphPage graph={context.graph} context={context} />}
        {activeView === "reports" && <ReportsPage context={context} focusedReportPath={context.focusedReportPath} />}
        {activeView === "tokens" && <TokensPage context={context} />}
        {activeView === "settings" && <ConfigPage context={context} />}
      </Suspense>
    </RouteErrorBoundary>
  );
}

export function SettingsRoute({ context }: { context: AppContext }) {
  const t = context.t;
  return (
    <Suspense fallback={<section className="panel page-loading"><LoadingBlock title={t("pageLoading")} copy={t("pageLoadingCopy")} /></section>}>
      <ConfigPage context={context} embedded />
    </Suspense>
  );
}
