import type { DesktopAppConfig } from "./config.js";
import type {
  DesktopDiagnostics,
  DesktopEnvironment,
  DesktopServiceState,
} from "../preload/types.js";

export function getDesktopEnvironment(): DesktopEnvironment {
  return {
    isDesktopApp: true,
    platform: process.platform,
    versions: {
      chrome: process.versions.chrome ?? "",
      electron: process.versions.electron ?? "",
      node: process.versions.node,
    },
  };
}

export function buildDesktopDiagnostics(input: {
  config: DesktopAppConfig;
  desktopLogPath?: string;
  environment?: DesktopEnvironment;
  serviceState: DesktopServiceState;
}): DesktopDiagnostics {
  const { config, desktopLogPath, serviceState } = input;
  return {
    appData:
      config.appServer.mode === "managed"
        ? {
            configPath: config.appServer.configPath,
            root: config.appServer.appDataRoot,
          }
        : undefined,
    environment: input.environment ?? getDesktopEnvironment(),
    logs: {
      desktopLogPath,
      serviceLogPath: serviceState.logPath,
    },
    service: serviceState,
  };
}
