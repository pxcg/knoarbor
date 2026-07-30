import type {
  DesktopCommand,
  DesktopEnvironment,
  DesktopPickerResult,
} from "../../../desktop/src/preload/types";

export function getDesktopBridge() {
  return window.knoarborDesktop ?? null;
}

export function isDesktopApp() {
  return Boolean(getDesktopBridge());
}

export function hasDesktopConfigBridge() {
  return Boolean(getDesktopBridge()?.config);
}

export async function readDesktopConfigRaw(configPath?: string | null): Promise<unknown> {
  return getDesktopBridge()?.config?.readRaw({ config_path: configPath || null });
}

export async function writeDesktopConfigRaw(configPath: string | null, content: string): Promise<unknown> {
  return getDesktopBridge()?.config?.writeRaw({ config_path: configPath, content });
}

export async function readDesktopConfigForm(configPath?: string | null): Promise<unknown> {
  return getDesktopBridge()?.config?.readForm({ config_path: configPath || null });
}

export async function writeDesktopConfigForm(configPath: string | null, payload: Record<string, unknown>): Promise<unknown> {
  return getDesktopBridge()?.config?.writeForm({ ...payload, config_path: configPath });
}

export async function readDesktopConfigDiagnostics(
  configPath?: string | null,
  options: { refreshSourceCounts?: boolean } = {},
): Promise<unknown> {
  return getDesktopBridge()?.config?.getDiagnostics({
    config_path: configPath || null,
    refresh_source_counts: options.refreshSourceCounts === true,
  });
}

export async function readDesktopVaults(configPath?: string | null): Promise<unknown> {
  return getDesktopBridge()?.config?.getVaults({ config_path: configPath || null });
}

export async function getDesktopEnvironment(): Promise<DesktopEnvironment | null> {
  return (await getDesktopBridge()?.getEnvironment()) ?? null;
}

export async function resolveDesktopServiceUrl(path: string): Promise<string | null> {
  const endpoint = (await getDesktopBridge()?.getServiceState())?.endpoint?.trim();
  if (!endpoint) return null;
  const base = endpoint.endsWith("/") ? endpoint : `${endpoint}/`;
  return new URL(path.replace(/^\/+/, ""), base).toString();
}

export function onDesktopCommand(listener: (command: DesktopCommand) => void) {
  return getDesktopBridge()?.onCommand(listener);
}

export async function restartDesktopService() {
  return getDesktopBridge()?.restartService();
}

export function canRestartDesktopService() {
  return Boolean(getDesktopBridge()?.restartService);
}

export async function openDesktopLogs() {
  return getDesktopBridge()?.openLogs();
}

export async function openDesktopPath(path: string) {
  if (!path) return { opened: false };
  return getDesktopBridge()?.openPath(path) ?? { opened: false };
}

export function canOpenDesktopPath() {
  return Boolean(getDesktopBridge()?.openPath);
}

export async function revealDesktopPath(path: string) {
  if (!path) return { opened: false };
  return getDesktopBridge()?.revealPath(path) ?? { opened: false };
}

export function canRevealDesktopPath() {
  return Boolean(getDesktopBridge()?.revealPath);
}

export async function selectDesktopDirectory(options?: { defaultPath?: string; title?: string }): Promise<DesktopPickerResult> {
  return getDesktopBridge()?.selectDirectory(options) ?? { canceled: true };
}

export function canSelectDesktopDirectory() {
  return Boolean(getDesktopBridge()?.selectDirectory);
}

export async function selectDesktopFile(options?: { defaultPath?: string; title?: string }): Promise<DesktopPickerResult> {
  return getDesktopBridge()?.selectFile(options) ?? { canceled: true };
}

export function canSelectDesktopFile() {
  return Boolean(getDesktopBridge()?.selectFile);
}
