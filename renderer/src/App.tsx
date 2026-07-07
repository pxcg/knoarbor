import { AppShell } from "./components/AppShell";
import { AppRoutes, SettingsRoute } from "./appRoutes";
import { SidebarRecentSessions } from "./components/SidebarRecentSessions";
import { WorkspaceSettingsModal } from "./components/WorkspaceSettingsModal";
import { useAppController } from "./useAppController";

export function App() {
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
    >
      <AppRoutes activeView={activeView} context={context} onNavigate={setActiveView} />
      <WorkspaceSettingsModal isOpen={workspaceSettingsOpen} t={t} onClose={() => setWorkspaceSettingsOpen(false)}>
        <SettingsRoute context={context} />
      </WorkspaceSettingsModal>
    </AppShell>
  );
}
