import { contextBridge, ipcRenderer } from "electron";
import type {
  DesktopCommand,
  DesktopServiceState,
  KnoArborDesktopBridge,
} from "./types.js";

const desktopApi: KnoArborDesktopBridge = {
  config: {
    getDiagnostics: (payload) =>
      ipcRenderer.invoke("knoarbor-desktop:config-diagnostics", payload),
    getVaults: (payload) =>
      ipcRenderer.invoke("knoarbor-desktop:vaults", payload),
    readForm: (payload) =>
      ipcRenderer.invoke("knoarbor-desktop:config-read-form", payload),
    readRaw: (payload) =>
      ipcRenderer.invoke("knoarbor-desktop:config-read-raw", payload),
    writeForm: (payload) =>
      ipcRenderer.invoke("knoarbor-desktop:config-write-form", payload),
    writeRaw: (payload) =>
      ipcRenderer.invoke("knoarbor-desktop:config-write-raw", payload),
  },
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
  openLogs: () => ipcRenderer.invoke("knoarbor-desktop:logs-open"),
  openPath: (path) => ipcRenderer.invoke("knoarbor-desktop:path-open", path),
  deleteDirectory: (path) => ipcRenderer.invoke("knoarbor-desktop:directory-delete", path),
  restartService: () => ipcRenderer.invoke("knoarbor-desktop:service-restart"),
  selectDirectory: (options) =>
    ipcRenderer.invoke("knoarbor-desktop:select-directory", options),
  selectFile: (options) =>
    ipcRenderer.invoke("knoarbor-desktop:select-file", options),
};

contextBridge.exposeInMainWorld("knoarborDesktop", desktopApi);
