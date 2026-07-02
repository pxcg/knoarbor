type DesktopPickerResult = {
  canceled: boolean;
  path?: string;
};

type DesktopEnvSecretSaveResult = {
  error?: string;
  path?: string;
  saved: string[];
};

export function getDesktopBridge() {
  return window.knoarborDesktop ?? null;
}

export function isDesktopApp() {
  return Boolean(getDesktopBridge());
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

export async function saveDesktopEnvSecrets(secrets: Record<string, string>): Promise<DesktopEnvSecretSaveResult> {
  return getDesktopBridge()?.saveEnvSecrets(secrets) ?? { saved: [] };
}

export function canSaveDesktopEnvSecrets() {
  return Boolean(getDesktopBridge()?.saveEnvSecrets);
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
