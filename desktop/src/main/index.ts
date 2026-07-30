import { electronApp, optimizer } from "@electron-toolkit/utils";
import { app, BrowserWindow } from "electron";
import log from "electron-log/main";
import { join } from "node:path";
import { optionalDesktopAppIconPath } from "./assets.js";
import {
  configureDesktopDataPaths,
  ensureDesktopBootstrapConfig,
  resolveDesktopAppConfig,
} from "./config.js";
import { registerDesktopIpc } from "./ipc.js";
import { installDesktopMenu } from "./menu.js";
import { desktopProduct } from "./product.js";
import {
  registerRendererProtocol,
  registerRendererProtocolScheme,
  rendererEntryUrl,
} from "./renderer-protocol.js";
import { DesktopServiceManager } from "./service-manager.js";
import { coordinateManagedServiceShutdown } from "./shutdown-coordinator.js";
import { DesktopWindowManager } from "./window-manager.js";

configureDesktopDataPaths();
registerRendererProtocolScheme();

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
  if (config.appServer.mode === "managed") {
    const appDataRoot = config.appServer.appDataRoot;
    log.transports.file.resolvePathFn = () => join(appDataRoot, "logs", "desktop.log");
  }
  log.initialize();
  electronApp.setAppUserModelId(config.appUserModelId);
  registerRendererProtocol({
    assetsRoot: config.appServer.mode === "managed" ? config.appServer.rendererAssetsRoot : config.rendererAssetsRoot,
    getServiceEndpoint: () => serviceManager.getState().endpoint,
  });
  const appIcon = optionalDesktopAppIconPath();
  if (process.platform === "darwin" && appIcon && app.dock) {
    app.dock.setIcon(appIcon);
  }
  ensureDesktopBootstrapConfig(config.appServer);
  installDesktopMenu({ helpUrl: desktopProduct.helpUrl });

  app.on("browser-window-created", (_, window) => {
    optimizer.watchWindowShortcuts(window);
  });

  await serviceManager.start(config.appServer);
  const rendererUrl = rendererEntryUrl();
  windowManager.createMainWindow(rendererUrl, { title: desktopProduct.name });
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      windowManager.createMainWindow(rendererUrl, { title: desktopProduct.name });
    }
  });
}

function handleFatalStartupError(error: unknown): void {
  log.error(error);
  app.quit();
}

coordinateManagedServiceShutdown(app, serviceManager, (error) => {
  log.error("Failed to stop the managed service before desktop shutdown", error);
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
