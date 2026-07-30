import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(desktopRoot, "..");
const rendererDist = resolve(repoRoot, "renderer/dist");
const rendererIndex = resolve(rendererDist, "index.html");

if (!existsSync(rendererIndex)) {
  throw new Error(
    `KnoArbor renderer build output is missing: ${rendererDist}. Run npm --prefix renderer run build first.`,
  );
}

console.log(`Using KnoArbor renderer build output: ${rendererDist}`);

