import { navCopy, viewTitles } from "../i18n";
import { LineIcon } from "./LineIcon";
import type { Language, ViewName } from "../types";

const navItems: ViewName[] = [
  "overview",
  "runs",
  "sources",
  "ingest",
  "lint",
  "query",
  "wiki",
  "graph",
  "reports",
  "settings",
  "docs",
];

type SidebarProps = {
  activeView: ViewName;
  collapsed: boolean;
  serviceOnline: boolean | null;
  language: Language;
  t: (key: string) => string;
  onChangeView: (view: ViewName) => void;
  onToggleCollapsed: () => void;
};

export function Sidebar({ activeView, collapsed, serviceOnline, language, t, onChangeView, onToggleCollapsed }: SidebarProps) {
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
        {navItems.map((item) => (
          <button
            key={item}
            className={`nav-item ${activeView === item ? "active" : ""}`}
            onClick={() => onChangeView(item)}
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
      </nav>
      <div className="sidebar-footer">
        <span className={`status-dot ${serviceOnline === true ? "online" : serviceOnline === false ? "offline" : ""}`} />
        <span className="sidebar-footer-text">{serviceOnline === true ? t("serviceOnline") : serviceOnline === false ? t("serviceOffline") : t("serviceChecking")}</span>
      </div>
    </aside>
  );
}
