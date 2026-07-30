import { rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(desktopRoot, "..");
const artifacts = [
  resolve(repositoryRoot, "renderer/dist"),
  resolve(desktopRoot, "out"),
  resolve(desktopRoot, "release"),
  resolve(desktopRoot, "resources/service"),
  resolve(desktopRoot, ".pyinstaller"),
];

for (const artifact of artifacts) {
  await rm(artifact, { force: true, recursive: true });
}

process.stdout.write("Removed generated desktop package artifacts.\n");

