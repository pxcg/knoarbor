/// <reference types="vite/client" />

type KnoArborDesktopCommand =
  | "chat.new"
  | "settings.open"
  | "service.restart"
  | "logs.open";

type KnoArborDesktopBridge = {
  config?: {
    getDiagnostics(payload?: Record<string, unknown>): Promise<unknown>;
    getVaults(payload?: Record<string, unknown>): Promise<unknown>;
    readForm(payload?: Record<string, unknown>): Promise<unknown>;
    readRaw(payload?: Record<string, unknown>): Promise<unknown>;
    writeForm(payload: Record<string, unknown>): Promise<unknown>;
    writeRaw(payload: Record<string, unknown>): Promise<unknown>;
  };
  getDiagnostics(): Promise<unknown>;
  getEnvironment(): Promise<unknown>;
  getServiceState(): Promise<unknown>;
  onCommand(listener: (command: KnoArborDesktopCommand) => void): () => void;
  onServiceStateChanged(listener: (state: unknown) => void): () => void;
  openLogs(): Promise<{ opened: boolean; path?: string }>;
  openPath(path: string): Promise<{ opened: boolean; path?: string; error?: string }>;
  deleteDirectory(path: string): Promise<{ deleted: boolean; path?: string; error?: string }>;
  restartService(): Promise<unknown>;
  selectDirectory(options?: { defaultPath?: string; title?: string }): Promise<{
    canceled: boolean;
    path?: string;
  }>;
  selectFile(options?: { defaultPath?: string; title?: string }): Promise<{
    canceled: boolean;
    path?: string;
  }>;
};

interface Window {
  knoarborDesktop?: KnoArborDesktopBridge;
}
