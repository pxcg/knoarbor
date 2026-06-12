import { navCopy, viewTitles } from "../i18n";
import { LineIcon } from "./LineIcon";
import type { Language, ViewName } from "../types";

const navItems: ViewName[] = [
  "chat",
  "runs",
  "sources",
  "ingest",
  "lint",
  "query",
  "wiki",
  "graph",
  "reports",
  "tokens",
  "docs",
];

const navGroups: Array<{ labelKey: string; items: ViewName[] }> = [
  { labelKey: "navGroupWorkspace", items: ["chat", "runs"] },
  { labelKey: "navGroupKnowledge", items: ["sources", "wiki", "graph"] },
  { labelKey: "navGroupPipelines", items: ["ingest", "lint", "query"] },
  { labelKey: "navGroupInsights", items: ["reports", "tokens"] },
  { labelKey: "navGroupSystem", items: ["docs"] },
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
};

export function Sidebar({ activeView, collapsed, serviceOnline, language, t, onChangeView, onPreloadView, onToggleCollapsed, onOpenWorkspaceSettings }: SidebarProps) {
  const logoUrl = `${import.meta.env.BASE_URL}knoarbor-logo.svg`;

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
      </div>
      <button className="sidebar-toggle" type="button" onClick={onToggleCollapsed} title={collapsed ? t("expandSidebar") : t("collapseSidebar")} aria-label={collapsed ? t("expandSidebar") : t("collapseSidebar")}>
        <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>
      </button>
      <nav className="nav" aria-label="Main navigation">
        {(collapsed ? [{ labelKey: "navGroupCollapsed", items: navItems }] : navGroups).map((group) => (
          <div className="nav-group" key={group.labelKey}>
            {!collapsed && <div className="nav-group-label">{t(group.labelKey)}</div>}
            {group.items.map((item) => (
              <button
                key={item}
                className={`nav-item ${activeView === item ? "active" : ""}`}
                onClick={() => onChangeView(item)}
                onFocus={() => onPreloadView?.(item)}
                onMouseEnter={() => onPreloadView?.(item)}
                title={collapsed ? viewTitles[language][item] : undefined}
              >
                <span className="nav-icon" aria-hidden="true">
                  <LineIcon name={item} />
                </span>
                <span className="nav-text">
                  <strong>{viewTitles[language][item]}</strong>
                  <span>{navCopy[language][item]}</span>
                </span>
              </button>
            ))}
          </div>
        ))}
      </nav>
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
