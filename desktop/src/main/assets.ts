import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDir = dirname(fileURLToPath(import.meta.url));
const resourcesDir = join(moduleDir, "../../resources");

export function desktopResourcePath(...parts: string[]): string {
  if (typeof process.resourcesPath === "string") {
    const packagedResourcePath = join(process.resourcesPath, ...parts);
    if (existsSync(packagedResourcePath)) return packagedResourcePath;
  }
  return join(resourcesDir, ...parts);
}

export function optionalDesktopResourcePath(...parts: string[]): string | undefined {
  const resourcePath = desktopResourcePath(...parts);
  return existsSync(resourcePath) ? resourcePath : undefined;
}

export function optionalDesktopAppIconPath(
  platform: NodeJS.Platform = process.platform,
): string | undefined {
  const fileName = platform === "win32" ? "icon-windows.png" : "icon.png";
  return optionalDesktopResourcePath("icons", fileName);
}
