import { mkdir, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const assetsDir = resolve(scriptDir, "../../src/knoarbor/ui/dist/assets");

await rm(assetsDir, { recursive: true, force: true });
await mkdir(assetsDir, { recursive: true });
