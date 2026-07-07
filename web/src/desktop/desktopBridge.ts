type DesktopPickerResult = {
  canceled: boolean;
  path?: string;
};

type DesktopEnvironment = {
  isDesktopApp: true;
  platform: string;
  versions: {
    chrome: string;
    electron: string;
    node: string;
  };
};

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
  return (await getDesktopBridge()?.getEnvironment()) as DesktopEnvironment | null;
}

export function onDesktopCommand(listener: (command: KnoArborDesktopCommand) => void) {
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

export async function deleteDesktopDirectory(path: string) {
  if (!path) return { deleted: false };
  return getDesktopBridge()?.deleteDirectory(path) ?? { deleted: false };
}

export function canDeleteDesktopDirectory() {
  return Boolean(getDesktopBridge()?.deleteDirectory);
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
