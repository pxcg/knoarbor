import { BrowserWindow, dialog, ipcMain, shell, type OpenDialogOptions } from "electron";
import log from "electron-log/main";
import { rm, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { parse, resolve } from "node:path";
import type { DesktopAppConfig } from "./config.js";
import type { DesktopServiceManager } from "./service-manager.js";
import type { DesktopEnvironment } from "../preload/types.js";

export function registerDesktopIpc(input: {
  config: DesktopAppConfig;
  serviceManager: DesktopServiceManager;
}): void {
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
  ipcMain.handle("knoarbor-desktop:directory-delete", async (_event, path?: string) => {
    const rawPath = String(path || "").trim();
    if (!rawPath) return { deleted: false, error: "Path is empty." };
    const target = resolve(rawPath);
    const root = parse(target).root;
    if (target === root || target === resolve(homedir())) {
      return { deleted: false, path: target, error: "Refusing to delete a protected directory." };
    }
    const targetStat = await stat(target).catch(() => null);
    if (!targetStat) return { deleted: true, path: target };
    if (!targetStat.isDirectory()) {
      return { deleted: false, path: target, error: "Path is not a directory." };
    }
    try {
      await rm(target, { recursive: true, force: true });
      return { deleted: true, path: target };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return { deleted: false, path: target, error: message };
    }
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
