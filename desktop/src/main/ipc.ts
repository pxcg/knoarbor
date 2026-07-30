import { BrowserWindow, dialog, ipcMain, shell, type OpenDialogOptions } from "electron";
import log from "electron-log/main";
import { spawn } from "node:child_process";
import { join } from "node:path";
import type { DesktopAppConfig } from "./config.js";
import type { DesktopServiceManager } from "./service-manager.js";
import type { DesktopEnvironment } from "../preload/types.js";

export function registerDesktopIpc(input: {
  config: DesktopAppConfig;
  serviceManager: DesktopServiceManager;
}): void {
  ipcMain.handle("knoarbor-desktop:config-read-raw", async (_event, payload?: Record<string, unknown>) =>
    runDesktopConfigCommand(input.config, "read-raw", payload),
  );
  ipcMain.handle("knoarbor-desktop:config-write-raw", async (_event, payload?: Record<string, unknown>) =>
    runDesktopConfigCommand(input.config, "write-raw", payload),
  );
  ipcMain.handle("knoarbor-desktop:config-read-form", async (_event, payload?: Record<string, unknown>) =>
    runDesktopConfigCommand(input.config, "read-form", payload),
  );
  ipcMain.handle("knoarbor-desktop:config-write-form", async (_event, payload?: Record<string, unknown>) =>
    runDesktopConfigCommand(input.config, "write-form", payload),
  );
  ipcMain.handle("knoarbor-desktop:config-diagnostics", async (_event, payload?: Record<string, unknown>) =>
    runDesktopConfigCommand(input.config, "diagnostics", payload),
  );
  ipcMain.handle("knoarbor-desktop:vaults", async (_event, payload?: Record<string, unknown>) =>
    runDesktopConfigCommand(input.config, "vaults", payload),
  );
  ipcMain.handle("knoarbor-desktop:environment", () => getEnvironment());
  ipcMain.handle("knoarbor-desktop:service-state", () =>
    input.serviceManager.getState(),
  );
  ipcMain.handle("knoarbor-desktop:diagnostics", () => ({
    appData:
      input.config.appServer.mode === "managed"
        ? {
            configPath: input.config.appServer.configPath,
            root: input.config.appServer.appDataRoot,
          }
        : undefined,
    environment: getEnvironment(),
    logs: {
      desktopLogPath: getLogFilePath(),
      serviceLogPath: input.serviceManager.getState().logPath,
    },
    service: input.serviceManager.getState(),
  }));
  ipcMain.handle("knoarbor-desktop:logs-open", async () => {
    const filePath = getLogFilePath();
    if (!filePath) return { opened: false };
    await shell.showItemInFolder(filePath);
    return { opened: true, path: filePath };
  });
  ipcMain.handle("knoarbor-desktop:path-open", async (_event, path?: string) => {
    const target = String(path || "").trim();
    if (!target) return { opened: false };
    const error = await shell.openPath(target);
    return error ? { opened: false, path: target, error } : { opened: true, path: target };
  });
  ipcMain.handle("knoarbor-desktop:path-reveal", async (_event, path?: string) => {
    const target = String(path || "").trim();
    if (!target) return { opened: false };
    shell.showItemInFolder(target);
    return { opened: true, path: target };
  });
  ipcMain.handle("knoarbor-desktop:service-restart", () =>
    input.serviceManager.restart(input.config.appServer),
  );
  ipcMain.handle(
    "knoarbor-desktop:select-directory",
    async (
      event,
      options?: {
        defaultPath?: string;
        title?: string;
      },
    ) => {
      const parent = BrowserWindow.fromWebContents(event.sender);
      const dialogOptions: OpenDialogOptions = {
        defaultPath: options?.defaultPath,
        properties: ["openDirectory", "createDirectory"],
        title: options?.title || "Choose Folder",
      };
      const result = parent
        ? await dialog.showOpenDialog(parent, dialogOptions)
        : await dialog.showOpenDialog(dialogOptions);
      return {
        canceled: result.canceled,
        path: result.filePaths[0],
      };
    },
  );
  ipcMain.handle(
    "knoarbor-desktop:select-file",
    async (
      event,
      options?: {
        defaultPath?: string;
        title?: string;
      },
    ) => {
      const parent = BrowserWindow.fromWebContents(event.sender);
      const dialogOptions: OpenDialogOptions = {
        defaultPath: options?.defaultPath,
        properties: ["openFile"],
        title: options?.title || "Choose File",
      };
      const result = parent
        ? await dialog.showOpenDialog(parent, dialogOptions)
        : await dialog.showOpenDialog(dialogOptions);
      return {
        canceled: result.canceled,
        path: result.filePaths[0],
      };
    },
  );
}

type DesktopConfigAction =
  | "diagnostics"
  | "read-form"
  | "read-raw"
  | "vaults"
  | "write-form"
  | "write-raw";

type DesktopConfigPayload = Record<string, unknown> & {
  config_path?: unknown;
  refresh_source_counts?: unknown;
};

async function runDesktopConfigCommand(
  config: DesktopAppConfig,
  action: DesktopConfigAction,
  payload: DesktopConfigPayload = {},
): Promise<unknown> {
  if (config.appServer.mode !== "managed") {
    throw new Error("Desktop config IPC is only available for managed desktop service mode.");
  }
  const commandPayload = {
    ...payload,
    config_path: typeof payload.config_path === "string" && payload.config_path.trim()
      ? payload.config_path
      : config.appServer.configPath,
  };
  const args = [
    ...config.appServer.serviceArgs,
    "--config",
    config.appServer.configPath,
    "desktop-config",
    action,
    "--json",
  ];
  if (action === "diagnostics" && commandPayload.refresh_source_counts === true) {
    args.push("--refresh-source-counts");
  }
  const stdout = await runJsonCommand({
    args,
    command: config.appServer.serviceCommand,
    cwd: config.appServer.serviceCwd,
    input: commandPayload,
  });
  return JSON.parse(stdout);
}

function runJsonCommand(input: {
  args: string[];
  command: string;
  cwd: string;
  input: DesktopConfigPayload;
}): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(input.command, input.args, {
      cwd: input.cwd,
      env: {
        ...process.env,
        KNOARBOR_DESKTOP: "1",
      },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve(stdout);
        return;
      }
      reject(new Error(stderr.trim() || stdout.trim() || `Desktop config command failed with exit code ${code}.`));
    });
    child.stdin.end(JSON.stringify(input.input));
  });
}

function getEnvironment(): DesktopEnvironment {
  return {
    isDesktopApp: true,
    platform: process.platform,
    versions: {
      chrome: process.versions.chrome,
      electron: process.versions.electron,
      node: process.versions.node,
    },
  };
}

function getLogFilePath(): string | undefined {
  const transports = log.transports as unknown as {
    file?: {
      getFile?: () => { path?: string };
    };
  };
  return transports.file?.getFile?.().path;
}
