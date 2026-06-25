import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDir = dirname(fileURLToPath(import.meta.url));
const resourcesDir = join(moduleDir, "../../resources");

export function desktopResourcePath(...parts: string[]): string {
  return join(resourcesDir, ...parts);
}

export function optionalDesktopResourcePath(...parts: string[]): string | undefined {
  const resourcePath = desktopResourcePath(...parts);
  return existsSync(resourcePath) ? resourcePath : undefined;
}
