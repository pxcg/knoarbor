import { lazy, Suspense, useRef } from "react";

import type { AppContext } from "./appContext";
import {
  chatCapabilities,
  configCapabilities,
  graphCapabilities,
  queryCapabilities,
  reportsCapabilities,
  runCapabilities,
  tokensCapabilities,
  wikiCapabilities,
} from "./appCapabilities";
import { LoadingBlock } from "./components/LoadingBlock";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import type { ViewName } from "./types";

const loadChatPage = () => import("./pages/ChatPage").then((module) => ({ default: module.ChatPage }));
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
  ingest: loadIngestPage,
  lint: loadLintPage,
  query: loadQueryPage,
  wiki: loadWikiPage,
  graph: loadGraphPage,
  reports: loadReportsPage,
  tokens: loadTokensPage,
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
const IngestPage = lazy(loadIngestPage);
const LintPage = lazy(loadLintPage);
const QueryPage = lazy(loadQueryPage);
const WikiPage = lazy(loadWikiPage);
const GraphPage = lazy(loadGraphPage);
const ReportsPage = lazy(loadReportsPage);
const TokensPage = lazy(loadTokensPage);
const ConfigPage = lazy(loadConfigPage);

export function AppRoutes({ activeView, context }: { activeView: ViewName; context: AppContext }) {
  const t = context.t;
  const mountedViews = useRef(new Set<ViewName>([activeView]));
  mountedViews.current.add(activeView);
  return (
    <>
      {Array.from(mountedViews.current).map((view) => (
        <div className="app-route" hidden={view !== activeView} key={view} aria-hidden={view !== activeView}>
          <RouteErrorBoundary
            fallbackTitle={t("routeLoadFailed")}
            fallbackCopy={t("routeLoadFailedCopy")}
            reloadLabel={t("reloadPage")}
          >
            <Suspense fallback={<section className="panel page-loading"><LoadingBlock title={t("pageLoading")} copy={t("pageLoadingCopy")} /></section>}>
              {renderRoute(view, context, view === activeView)}
            </Suspense>
          </RouteErrorBoundary>
        </div>
      ))}
    </>
  );
}

function renderRoute(view: ViewName, context: AppContext, active: boolean) {
  if (view === "chat") return <ChatPage context={chatCapabilities(context)} />;
  if (view === "wiki") return <WikiPage active={active} context={wikiCapabilities(context)} />;
  if (view === "ingest") return <IngestPage active={active} context={runCapabilities(context)} />;
  if (view === "lint") return <LintPage active={active} context={runCapabilities(context)} />;
  if (view === "query") return <QueryPage context={queryCapabilities(context)} />;
  if (view === "graph") return <GraphPage active={active} graph={context.graph} context={graphCapabilities(context)} />;
  if (view === "reports") return <ReportsPage active={active} context={reportsCapabilities(context)} />;
  if (view === "tokens") return <TokensPage active={active} context={tokensCapabilities(context)} />;
  return null;
}

export function SettingsRoute({ context }: { context: AppContext }) {
  return (
    <Suspense fallback={<section className="panel page-loading"><LoadingBlock title={context.t("pageLoading")} copy={context.t("pageLoadingCopy")} /></section>}>
      <ConfigPage context={configCapabilities(context)} embedded />
    </Suspense>
  );
}
