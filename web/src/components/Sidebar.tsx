import { navCopy, viewTitles } from "../i18n";
import { LineIcon } from "./LineIcon";
import type { Language, ViewName } from "../types";
import type { ReactNode } from "react";

export type PrimaryNavId = "chat" | "flows" | "knowledge" | "docs";

type PrimaryNavItem = {
  id: "flows" | "knowledge" | "docs";
  icon: ViewName;
  labelKey: string;
  subtitleKey: string;
  target: ViewName;
  items: ViewName[];
};

const primaryNavItems: PrimaryNavItem[] = [
  {
    id: "flows",
    icon: "runs",
    labelKey: "navCollectionFlows",
    subtitleKey: "navCollectionFlowsCopy",
    target: "runs",
    items: ["runs", "ingest", "lint", "query", "reports", "tokens"],
  },
  {
    id: "knowledge",
    icon: "wiki",
    labelKey: "navCollectionKnowledge",
    subtitleKey: "navCollectionKnowledgeCopy",
    target: "wiki",
    items: ["wiki", "graph"],
  },
  {
    id: "docs",
    icon: "docs",
    labelKey: "navCollectionDocs",
    subtitleKey: "navCollectionDocsCopy",
    target: "docs",
    items: ["docs"],
  },
];

type SidebarProps = {
  activeView: ViewName;
  collapsed: boolean;
  serviceOnline: boolean | null;
  language: Language;
  t: (key: string) => string;
  onChangeView: (view: ViewName) => void;
  onPreloadView?: (view: ViewName) => void;
  onToggleCollapsed: () => void;
  onOpenWorkspaceSettings: () => void;
  sidebarSlot?: ReactNode;
};

export function Sidebar({ activeView, collapsed, serviceOnline, language, t, onChangeView, onPreloadView, onToggleCollapsed, onOpenWorkspaceSettings, sidebarSlot }: SidebarProps) {
  const logoUrl = `${import.meta.env.BASE_URL}knoarbor-logo.svg`;
  const activePrimary = primaryNavForView(activeView);

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          <img src={logoUrl} alt="" />
        </div>
        <div className="brand-copy">
          <div className="brand-title">KnoArbor</div>
          <div className="brand-subtitle">{t("appTagline")}</div>
        </div>
        <button className="sidebar-toggle" type="button" onClick={onToggleCollapsed} title={collapsed ? t("expandSidebar") : t("collapseSidebar")} aria-label={collapsed ? t("expandSidebar") : t("collapseSidebar")}>
          <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>
        </button>
      </div>
      <nav className="nav" aria-label="Main navigation">
        <button
          className={`nav-item ${activeView === "chat" ? "active" : ""}`}
          onClick={() => onChangeView("chat")}
          onFocus={() => onPreloadView?.("chat")}
          onMouseEnter={() => onPreloadView?.("chat")}
          title={collapsed ? viewTitles[language].chat : undefined}
        >
          <span className="nav-icon" aria-hidden="true">
            <LineIcon name="chat" />
          </span>
          <span className="nav-text">
            <strong>{viewTitles[language].chat}</strong>
            <span>{navCopy[language].chat}</span>
          </span>
        </button>
        {primaryNavItems.map((item) => {
          const active = activePrimary === item.id;
          return (
            <button
              key={item.id}
              className={`nav-item ${active ? "active" : ""}`}
              onClick={() => onChangeView(active ? activeView : item.target)}
              onFocus={() => onPreloadView?.(item.target)}
              onMouseEnter={() => onPreloadView?.(item.target)}
              title={collapsed ? t(item.labelKey) : undefined}
            >
              <span className="nav-icon" aria-hidden="true">
                <LineIcon name={item.icon} />
              </span>
              <span className="nav-text">
                <strong>{t(item.labelKey)}</strong>
                <span>{t(item.subtitleKey)}</span>
              </span>
            </button>
          );
        })}
      </nav>
      <div className="sidebar-chat-slot" id="knoarbor-sidebar-chat-slot">
        {sidebarSlot}
      </div>
      <div className="sidebar-footer">
        <button
          className="workspace-settings-trigger"
          type="button"
          onClick={onOpenWorkspaceSettings}
          title={t("workspaceSettings")}
          aria-label={t("workspaceSettings")}
        >
          <span className={`status-dot ${serviceOnline === true ? "online" : serviceOnline === false ? "offline" : ""}`} />
          <span className="sidebar-footer-text">{t("workspaceSettings")}</span>
          <span className="sidebar-footer-icon" aria-hidden="true">
            <LineIcon name="settings" />
          </span>
        </button>
      </div>
    </aside>
  );
}

function primaryNavForView(view: ViewName): PrimaryNavId {
  if (view === "chat") return "chat";
  if (view === "wiki" || view === "graph") return "knowledge";
  if (view === "docs") return "docs";
  return "flows";
}
