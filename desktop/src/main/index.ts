import { electronApp, optimizer } from "@electron-toolkit/utils";
import { app, BrowserWindow } from "electron";
import log from "electron-log/main";
import { optionalDesktopResourcePath } from "./assets.js";
import {
  configureDesktopUserDataPath,
  ensureDesktopBootstrapConfig,
  resolveDesktopAppConfig,
} from "./config.js";
import { registerDesktopIpc } from "./ipc.js";
import { installDesktopMenu } from "./menu.js";
import {
  registerRendererProtocol,
  registerRendererProtocolScheme,
  rendererEntryUrl,
} from "./renderer-protocol.js";
import { DesktopServiceManager } from "./service-manager.js";
import { DesktopWindowManager } from "./window-manager.js";
import { desktopProduct } from "./product.js";

configureDesktopUserDataPath();
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
  log.initialize();
  electronApp.setAppUserModelId(config.appUserModelId);
  registerRendererProtocol({
    assetsRoot: config.rendererAssetsRoot,
    getServiceEndpoint: () => serviceManager.getState().endpoint,
  });
  const appIcon = optionalDesktopResourcePath("icons", "icon.png");
  if (process.platform === "darwin" && appIcon && app.dock) {
    app.dock.setIcon(appIcon);
  }
  ensureDesktopBootstrapConfig(config.appServer);
  installDesktopMenu({ githubUrl: desktopProduct.helpUrl });

  app.on("browser-window-created", (_, window) => {
    optimizer.watchWindowShortcuts(window);
  });

  await serviceManager.start(config.appServer);
  const rendererUrl = rendererEntryUrl();
  windowManager.createMainWindow(rendererUrl);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      windowManager.createMainWindow(rendererUrl);
    }
  });
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
