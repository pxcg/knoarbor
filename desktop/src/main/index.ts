import { electronApp, optimizer } from "@electron-toolkit/utils";
import { app, BrowserWindow } from "electron";
import log from "electron-log/main";
import { optionalDesktopResourcePath } from "./assets.js";
import { ensureDesktopBootstrapConfig, resolveDesktopAppConfig } from "./config.js";
import { registerDesktopIpc } from "./ipc.js";
import { installDesktopMenu } from "./menu.js";
import { DesktopServiceManager } from "./service-manager.js";
import { DesktopWindowManager } from "./window-manager.js";

const appDataRootOverride = process.env.KNOARBOR_DESKTOP_APP_DATA_ROOT?.trim();
if (appDataRootOverride) {
  app.setPath("userData", appDataRootOverride);
}

const config = resolveDesktopAppConfig();
const serviceManager = new DesktopServiceManager();
const windowManager = new DesktopWindowManager();

const singleInstanceLock = app.requestSingleInstanceLock();
if (!singleInstanceLock) {
  app.quit();
}

serviceManager.onStateChanged((state) => windowManager.sendServiceState(state));
registerDesktopIpc({ config, serviceManager });

if (singleInstanceLock) {
  app.on("second-instance", () => windowManager.focusMainWindow());
  app.whenReady().then(startDesktopApp).catch(handleFatalStartupError);
}

async function startDesktopApp(): Promise<void> {
  log.initialize();
  electronApp.setAppUserModelId(config.appUserModelId);
  const appIcon = optionalDesktopResourcePath("icons", "icon.png");
  if (process.platform === "darwin" && appIcon && app.dock) {
    app.dock.setIcon(appIcon);
  }
  ensureDesktopBootstrapConfig(config.appServer);
  installDesktopMenu({ githubUrl: "https://github.com/pxcg/knoarbor" });

  app.on("browser-window-created", (_, window) => {
    optimizer.watchWindowShortcuts(window);
  });

  const serviceState = await serviceManager.start(config.appServer);
  const endpoint =
    serviceState.status === "healthy" && serviceState.endpoint
      ? serviceState.endpoint
      : rendererFallbackUrl();
  windowManager.createMainWindow(endpoint);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      windowManager.createMainWindow(endpoint);
    }
  });
}

function rendererFallbackUrl(): string {
  const fallback = new URL("../renderer/index.html", import.meta.url);
  return fallback.toString();
}

function handleFatalStartupError(error: unknown): void {
  log.error(error);
  app.quit();
}

app.on("before-quit", () => {
  void serviceManager.stop();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
