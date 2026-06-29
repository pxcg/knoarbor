import { contextBridge, ipcRenderer } from "electron";
import type {
  DesktopCommand,
  DesktopServiceState,
  KnoArborDesktopBridge,
} from "./types.js";

const desktopApi: KnoArborDesktopBridge = {
  getDiagnostics: () => ipcRenderer.invoke("knoarbor-desktop:diagnostics"),
  getEnvironment: () => ipcRenderer.invoke("knoarbor-desktop:environment"),
  getServiceState: () => ipcRenderer.invoke("knoarbor-desktop:service-state"),
  onCommand: (listener) => {
    const handler = (_event: Electron.IpcRendererEvent, command: DesktopCommand) => {
      listener(command);
    };
    ipcRenderer.on("knoarbor-desktop:command", handler);
    return () => ipcRenderer.removeListener("knoarbor-desktop:command", handler);
  },
  onServiceStateChanged: (listener) => {
    const handler = (_event: Electron.IpcRendererEvent, state: DesktopServiceState) => {
      listener(state);
    };
    ipcRenderer.on("knoarbor-desktop:service-state-changed", handler);
    return () =>
      ipcRenderer.removeListener("knoarbor-desktop:service-state-changed", handler);
  },
  openApiDocs: () => ipcRenderer.invoke("knoarbor-desktop:api-docs-open"),
  openLogs: () => ipcRenderer.invoke("knoarbor-desktop:logs-open"),
  openPath: (path) => ipcRenderer.invoke("knoarbor-desktop:path-open", path),
  restartService: () => ipcRenderer.invoke("knoarbor-desktop:service-restart"),
  saveEnvSecrets: (secrets) =>
    ipcRenderer.invoke("knoarbor-desktop:env-secrets-save", secrets),
  selectDirectory: (options) =>
    ipcRenderer.invoke("knoarbor-desktop:select-directory", options),
};

contextBridge.exposeInMainWorld("knoarborDesktop", desktopApi);
