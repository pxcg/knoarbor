import { mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(desktopRoot, "..");
const serviceEntry = resolve(desktopRoot, "service/knoar_service.py");
const workPath = resolve(desktopRoot, ".pyinstaller");
const distPath = resolve(desktopRoot, "resources/service");
const specPath = resolve(workPath, "spec");

await rm(distPath, { force: true, recursive: true });
await rm(workPath, { force: true, recursive: true });
await mkdir(distPath, { recursive: true });
await mkdir(specPath, { recursive: true });

const args = [
  "run",
  "--with",
  "pyinstaller==6.11.1",
  "pyinstaller",
  "--clean",
  "--noconfirm",
  "--onefile",
  "--name",
  "knoar-service",
  "--paths",
  resolve(repoRoot, "src"),
  "--collect-data",
  "knoarbor",
  "--distpath",
  distPath,
  "--workpath",
  resolve(workPath, "build"),
  "--specpath",
  specPath,
  serviceEntry,
];

await run("uv", args, repoRoot);
console.log(`Built KnoArbor service artifact: ${distPath}`);

function run(command, args, cwd) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: process.env,
      stdio: "inherit",
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      reject(new Error(`${command} ${args.join(" ")} exited with ${code}`));
    });
  });
}
