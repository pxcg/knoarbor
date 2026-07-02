import { LineIcon } from "./LineIcon";
import { Sidebar } from "./Sidebar";
import { navCopy, viewSubtitles, viewTitles } from "../i18n";
import type { Language, ViewName } from "../types";
import type { ReactNode } from "react";

type AppShellProps = {
  activeView: ViewName;
  children: ReactNode;
  language: Language;
  serviceOnline: boolean | null;
  sidebarCollapsed: boolean;
  t: (key: string) => string;
  onChangeView: (view: ViewName) => void;
  onPreloadView?: (view: ViewName) => void;
  onToggleSidebar: () => void;
  onOpenWorkspaceSettings: () => void;
  sidebarSlot?: ReactNode;
};

export function AppShell({
  activeView,
  children,
  language,
  serviceOnline,
  sidebarCollapsed,
  t,
  onChangeView,
  onPreloadView,
  onToggleSidebar,
  onOpenWorkspaceSettings,
  sidebarSlot,
}: AppShellProps) {
  const secondaryItems = secondaryNavItems(activeView);

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <Sidebar
        activeView={activeView}
        collapsed={sidebarCollapsed}
        serviceOnline={serviceOnline}
        language={language}
        t={t}
        onChangeView={onChangeView}
        onPreloadView={onPreloadView}
        onToggleCollapsed={onToggleSidebar}
        onOpenWorkspaceSettings={onOpenWorkspaceSettings}
        sidebarSlot={sidebarSlot}
      />
      <main className="main">
        <header className="topbar">
          <div className="topbar-heading">
            <p className="topbar-kicker">{viewTitles[language][activeView]}</p>
            {activeView !== "chat" && <p className="topbar-subtitle">{viewSubtitles[language][activeView]}</p>}
          </div>
          <div className="topbar-actions">
            <a className="button icon-button" href="https://github.com/pxcg/knoarbor" target="_blank" rel="noreferrer" aria-label="GitHub">
              <LineIcon name="github" />
            </a>
          </div>
        </header>
        {secondaryItems.length > 1 && (
          <nav className="secondary-nav" aria-label={t("secondaryNavigation")}>
            {secondaryItems.map((item) => (
              <button
                key={item}
                className={`secondary-nav-item ${activeView === item ? "active" : ""}`}
                type="button"
                onClick={() => onChangeView(item)}
                onFocus={() => onPreloadView?.(item)}
                onMouseEnter={() => onPreloadView?.(item)}
              >
                <LineIcon name={item} />
                <span>
                  <strong>{viewTitles[language][item]}</strong>
                  <small>{navCopy[language][item]}</small>
                </span>
              </button>
            ))}
          </nav>
        )}
        <div className="main-content">
          {children}
        </div>
      </main>
    </div>
  );
}

function secondaryNavItems(activeView: ViewName): ViewName[] {
  if (activeView === "wiki" || activeView === "graph") return ["wiki", "graph"];
  if (activeView === "chat") return [];
  return ["runs", "ingest", "lint", "query", "reports", "tokens"];
}
