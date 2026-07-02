export type DesktopEnvironment = {
  isDesktopApp: true;
  platform: NodeJS.Platform;
  versions: {
    chrome: string;
    electron: string;
    node: string;
  };
};

export type DesktopServiceMode = "external" | "managed";

export type DesktopServiceStatus =
  | "idle"
  | "starting"
  | "healthy"
  | "stopping"
  | "stopped"
  | "failed";

export type DesktopServiceState = {
  command?: string;
  configPath?: string;
  endpoint?: string;
  exitCode?: number | null;
  lastOutput?: string[];
  lastError?: string;
  logDir?: string;
  logPath?: string;
  mode: DesktopServiceMode;
  port?: number;
  signal?: NodeJS.Signals | null;
  startedAt?: string;
  stateDir?: string;
  status: DesktopServiceStatus;
};

export type DesktopDiagnostics = {
  appData?: {
    configPath?: string;
    envPath?: string;
    root?: string;
  };
  environment: DesktopEnvironment;
  logs: {
    desktopLogPath?: string;
    serviceLogPath?: string;
  };
  service: DesktopServiceState;
};

export type DesktopCommand =
  | "chat.new"
  | "settings.open"
  | "service.restart"
  | "logs.open";

export type KnoArborDesktopBridge = {
  getDiagnostics(): Promise<DesktopDiagnostics>;
  getEnvironment(): Promise<DesktopEnvironment>;
  getServiceState(): Promise<DesktopServiceState>;
  onCommand(listener: (command: DesktopCommand) => void): () => void;
  onServiceStateChanged(listener: (state: DesktopServiceState) => void): () => void;
  openLogs(): Promise<{ opened: boolean; path?: string }>;
  openPath(path: string): Promise<{ opened: boolean; path?: string; error?: string }>;
  restartService(): Promise<DesktopServiceState>;
  saveEnvSecrets(secrets: Record<string, string>): Promise<{
    error?: string;
    path?: string;
    saved: string[];
  }>;
  selectDirectory(options?: { defaultPath?: string; title?: string }): Promise<{
    canceled: boolean;
    path?: string;
  }>;
  selectFile(options?: { defaultPath?: string; title?: string }): Promise<{
    canceled: boolean;
    path?: string;
  }>;
};

declare global {
  interface Window {
    knoarborDesktop?: KnoArborDesktopBridge;
  }
}
