import { BrowserWindow, shell } from "electron";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { optionalDesktopAppIconPath } from "./assets.js";

const moduleDir = dirname(fileURLToPath(import.meta.url));

export class DesktopWindowManager {
  private mainWindow?: BrowserWindow;

  createMainWindow(url: string, input: { title: string }): BrowserWindow {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.focusMainWindow();
      return this.mainWindow;
    }

    const window = new BrowserWindow({
      backgroundColor: "#ffffff",
      height: 900,
      icon: optionalDesktopAppIconPath(),
      minHeight: 720,
      minWidth: 1080,
      show: false,
      title: input.title,
      titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
      trafficLightPosition:
        process.platform === "darwin" ? { x: 18, y: 18 } : undefined,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        preload: join(moduleDir, "../preload/index.mjs"),
        sandbox: false,
      },
      width: 1360,
    });

    window.once("ready-to-show", () => window.show());
    window.webContents.setWindowOpenHandler(({ url: externalUrl }) => {
      void shell.openExternal(externalUrl);
      return { action: "deny" };
    });

    void window.loadURL(url);
    this.mainWindow = window;
    window.once("closed", () => {
      if (this.mainWindow === window) {
        this.mainWindow = undefined;
      }
    });
    return window;
  }

  focusMainWindow(): void {
    const window = this.mainWindow;
    if (!window || window.isDestroyed()) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
  }

  sendCommand(command: string): void {
    const window = this.mainWindow;
    if (!window || window.isDestroyed()) return;
    window.webContents.send("knoarbor-desktop:command", command);
  }

  sendServiceState(state: unknown): void {
    const window = this.mainWindow;
    if (!window || window.isDestroyed()) return;
    window.webContents.send("knoarbor-desktop:service-state-changed", state);
  }

}
