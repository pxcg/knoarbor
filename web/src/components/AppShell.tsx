import { LineIcon } from "./LineIcon";
import { Sidebar } from "./Sidebar";
import { viewSubtitles, viewTitles } from "../i18n";
import type { Language, ViewName } from "../types";
import type { ReactNode } from "react";

type AppShellProps = {
  activeView: ViewName;
  children: ReactNode;
  isRefreshing: boolean;
  language: Language;
  serviceOnline: boolean | null;
  sidebarCollapsed: boolean;
  t: (key: string) => string;
  onChangeView: (view: ViewName) => void;
  onPreloadView?: (view: ViewName) => void;
  onRefresh: () => void;
  onSetLanguage: (language: Language) => void;
  onToggleSidebar: () => void;
};

export function AppShell({
  activeView,
  children,
  isRefreshing,
  language,
  serviceOnline,
  sidebarCollapsed,
  t,
  onChangeView,
  onPreloadView,
  onRefresh,
  onSetLanguage,
  onToggleSidebar,
}: AppShellProps) {
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
      />
      <main className="main">
        <header className="topbar">
          <div className="topbar-heading">
            <p className="topbar-kicker">{viewTitles[language][activeView]}</p>
            <p className="topbar-subtitle">{viewSubtitles[language][activeView]}</p>
          </div>
          <div className="topbar-actions">
            <div className="language-switch" aria-label={t("language")}>
              <button className={language === "en" ? "active" : ""} onClick={() => onSetLanguage("en")} type="button">
                EN
              </button>
              <button className={language === "zh" ? "active" : ""} onClick={() => onSetLanguage("zh")} type="button">
                中文
              </button>
            </div>
            <button className="button secondary" onClick={onRefresh} disabled={isRefreshing}>
              {isRefreshing ? t("refreshing") : t("refresh")}
            </button>
            <a className="button icon-button" href="https://github.com/pxcg/knoarbor" target="_blank" rel="noreferrer" aria-label="GitHub">
              <LineIcon name="github" />
            </a>
            <a className="button ghost" href="/docs" target="_blank" rel="noreferrer">
              {t("apiDocs")}
            </a>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
