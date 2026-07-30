import { AppShell } from "./components/AppShell";
import { PageVaultSwitcher } from "./components/PageVaultSwitcher";
import { AppRoutes, SettingsRoute } from "./appRoutes";
import { SidebarRecentSessions } from "./components/SidebarRecentSessions";
import { WorkspaceSettingsModal } from "./components/WorkspaceSettingsModal";
import { useAppController } from "./useAppController";

export function App() {
  useTransientScrollbars();
  const {
    activeView,
    context,
    language,
    preloadView,
    serviceOnline,
    setActiveView,
    setWorkspaceSettingsOpen,
    sidebarCollapsed,
    t,
    toggleSidebar,
    workspaceSettingsOpen,
  } = useAppController();

  return (
    <AppShell
      activeView={activeView}
      language={language}
      serviceOnline={serviceOnline}
      sidebarCollapsed={sidebarCollapsed}
      t={t}
      onChangeView={setActiveView}
      onPreloadView={preloadView}
      onToggleSidebar={toggleSidebar}
      onOpenWorkspaceSettings={() => setWorkspaceSettingsOpen(true)}
      sidebarSlot={<SidebarRecentSessions context={context} />}
      secondaryAction={activeView !== "chat" && activeView !== "query" ? (
        <PageVaultSwitcher
          activeVaultId={context.activeVaultId}
          label={t("activeVault")}
          onChange={context.setActiveVaultId}
          vaultOptions={context.vaultOptions}
        />
      ) : null}
    >
      <AppRoutes activeView={activeView} context={context} />
      <WorkspaceSettingsModal isOpen={workspaceSettingsOpen} t={t} onClose={() => setWorkspaceSettingsOpen(false)}>
        <SettingsRoute context={context} />
      </WorkspaceSettingsModal>
    </AppShell>
  );
}

function useTransientScrollbars() {
  useEffect(() => {
    let timer: number | undefined;
    const showScrollbar = () => {
      document.documentElement.classList.add("is-scrolling");
      window.clearTimeout(timer);
      timer = window.setTimeout(() => document.documentElement.classList.remove("is-scrolling"), 700);
    };
    document.addEventListener("scroll", showScrollbar, true);
    return () => {
      document.removeEventListener("scroll", showScrollbar, true);
      window.clearTimeout(timer);
      document.documentElement.classList.remove("is-scrolling");
    };
  }, []);
}
import { useEffect } from "react";
