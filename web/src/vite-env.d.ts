/// <reference types="vite/client" />

type KnoArborDesktopCommand =
  | "chat.new"
  | "docs.open"
  | "settings.open"
  | "service.restart"
  | "logs.open";

type KnoArborDesktopBridge = {
  getDiagnostics(): Promise<unknown>;
  getEnvironment(): Promise<unknown>;
  getServiceState(): Promise<unknown>;
  onCommand(listener: (command: KnoArborDesktopCommand) => void): () => void;
  onServiceStateChanged(listener: (state: unknown) => void): () => void;
  openApiDocs(): Promise<{ opened: boolean; url?: string }>;
  openLogs(): Promise<{ opened: boolean; path?: string }>;
  openPath(path: string): Promise<{ opened: boolean; path?: string; error?: string }>;
  restartService(): Promise<unknown>;
  selectDirectory(options?: { defaultPath?: string; title?: string }): Promise<{
    canceled: boolean;
    path?: string;
  }>;
};

interface Window {
  knoarborDesktop?: KnoArborDesktopBridge;
}
