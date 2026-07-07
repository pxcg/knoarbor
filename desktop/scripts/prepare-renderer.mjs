import { cp, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(desktopRoot, "..");
const rendererDist = resolve(repoRoot, "renderer/dist");
const desktopRendererResources = resolve(desktopRoot, "resources/renderer");

if (!existsSync(resolve(rendererDist, "index.html"))) {
  throw new Error(
    `KnoArbor renderer build output is missing: ${rendererDist}. Run npm --prefix renderer run build first.`,
  );
}

await rm(desktopRendererResources, { force: true, recursive: true });
await mkdir(desktopRendererResources, { recursive: true });
await cp(rendererDist, desktopRendererResources, { recursive: true });

console.log(`Prepared KnoArbor Desktop renderer resources: ${desktopRendererResources}`);
