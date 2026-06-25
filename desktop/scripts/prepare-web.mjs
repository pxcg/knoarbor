import { cp, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(desktopRoot, "..");
const bundledUiDist = resolve(repoRoot, "src/knoarbor/ui/dist");
const desktopWebResources = resolve(desktopRoot, "resources/web");

if (!existsSync(resolve(bundledUiDist, "index.html"))) {
  throw new Error(
    `KnoArbor UI build output is missing: ${bundledUiDist}. Run npm --prefix web run build first.`,
  );
}

await rm(desktopWebResources, { force: true, recursive: true });
await mkdir(desktopWebResources, { recursive: true });
await cp(bundledUiDist, desktopWebResources, { recursive: true });

console.log(`Prepared KnoArbor Desktop web resources: ${desktopWebResources}`);

