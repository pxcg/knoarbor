import { LineIcon } from "./LineIcon";
import { Sidebar } from "./Sidebar";
import { navCopy, viewTitles } from "../i18n";
import { productIdentity } from "../product";
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
  secondaryAction?: ReactNode;
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
  secondaryAction,
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
        {(activeView !== "chat" || (productIdentity.showHelpLink && productIdentity.helpUrl)) && (
          <header className="topbar">
            {activeView !== "chat" && (
              <div className="topbar-heading">
                <p className="topbar-kicker">{viewTitles[language][activeView]}</p>
              </div>
            )}
            {productIdentity.showHelpLink && productIdentity.helpUrl && (
              <div className="topbar-actions">
                <a className="button icon-button" href={productIdentity.helpUrl} target="_blank" rel="noreferrer" aria-label="Help">
                  <LineIcon name="github" />
                </a>
              </div>
            )}
          </header>
        )}
        {secondaryItems.length > 1 && (
          <div className="secondary-nav-row">
            <nav className="secondary-nav" aria-label={t("secondaryNavigation")}>
              {secondaryItems.map((item) => (
                <button
                  key={item}
                  className={`secondary-nav-item ${activeView === item ? "active" : ""}`}
                  type="button"
                  onClick={() => onChangeView(item)}
                  onFocus={() => onPreloadView?.(item)}
                  onMouseEnter={() => onPreloadView?.(item)}
                  title={`${viewTitles[language][item]} · ${navCopy[language][item]}`}
                >
                  <LineIcon name={item} />
                  <span>
                    <strong>{viewTitles[language][item]}</strong>
                  </span>
                </button>
              ))}
            </nav>
            {secondaryAction}
          </div>
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
  return ["ingest", "lint", "query", "reports", "tokens"];
}
