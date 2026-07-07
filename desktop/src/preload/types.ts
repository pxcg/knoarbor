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
  config: {
    getDiagnostics(payload?: Record<string, unknown>): Promise<unknown>;
    getVaults(payload?: Record<string, unknown>): Promise<unknown>;
    readForm(payload?: Record<string, unknown>): Promise<unknown>;
    readRaw(payload?: Record<string, unknown>): Promise<unknown>;
    writeForm(payload: Record<string, unknown>): Promise<unknown>;
    writeRaw(payload: Record<string, unknown>): Promise<unknown>;
  };
  getDiagnostics(): Promise<DesktopDiagnostics>;
  getEnvironment(): Promise<DesktopEnvironment>;
  getServiceState(): Promise<DesktopServiceState>;
  onCommand(listener: (command: DesktopCommand) => void): () => void;
  onServiceStateChanged(listener: (state: DesktopServiceState) => void): () => void;
  openLogs(): Promise<{ opened: boolean; path?: string }>;
  openPath(path: string): Promise<{ opened: boolean; path?: string; error?: string }>;
  deleteDirectory(path: string): Promise<{ deleted: boolean; path?: string; error?: string }>;
  restartService(): Promise<DesktopServiceState>;
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
