import { execFile, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const root = path.resolve(import.meta.dirname, "..");
const checkOnly = process.argv.includes("--check");
const source = JSON.parse(
  await readFile(path.join(root, "harness/core-source.json"), "utf8"),
);

if (
  source.schemaVersion !== "development_harness.core_source.v1" ||
  source.package !== "@development-harness/core" ||
  source.path !== "../development-harness" ||
  !/^\d+\.\d+\.\d+$/u.test(source.version) ||
  !/^[a-f0-9]{40}$/u.test(source.commit) ||
  source.artifact !==
    "harness/vendor/development-harness-core-0.11.0.tgz" ||
  !/^[a-f0-9]{64}$/u.test(source.artifactSha256)
)
  throw new Error("harness/core-source.json is invalid");

const coreRoot = path.resolve(root, source.path);
const artifact = await readFile(path.join(root, source.artifact));
if (
  createHash("sha256").update(artifact).digest("hex") !==
  source.artifactSha256
)
  throw new Error("Vendored Harness Core artifact differs from its source pin");

let sourceManifest;
let sourceAvailable = true;
try {
  sourceManifest = JSON.parse(
    await readFile(path.join(coreRoot, "package.json"), "utf8"),
  );
} catch (error) {
  if (error?.code === "ENOENT") sourceAvailable = false;
  else throw error;
}
if (sourceAvailable) {
  if (
    sourceManifest.name !== source.package ||
    sourceManifest.version !== source.version
  )
    throw new Error(
      `Development Harness Core source must be ${source.package}@${source.version}`,
    );
  const head = await git(coreRoot, ["rev-parse", "HEAD"]);
  if (head !== source.commit)
    throw new Error(
      `Development Harness Core source must be at ${source.commit}; found ${head}`,
    );
  if (
    (await git(coreRoot, [
      "status",
      "--porcelain",
      "--untracked-files=all",
    ])) !== ""
  )
    throw new Error("Development Harness Core source worktree must be clean");
}

if (!checkOnly) await runPnpm(root, ["install", "--frozen-lockfile"]);

const installedManifest = JSON.parse(
  await readFile(
    path.join(
      root,
      "harness/node_modules/@development-harness/core/package.json",
    ),
    "utf8",
  ),
);
if (
  installedManifest.name !== source.package ||
  installedManifest.version !== source.version
)
  throw new Error(
    `Installed Harness Core must be ${source.package}@${source.version}`,
  );

if (sourceAvailable) {
  if (!checkOnly)
    await runPnpm(coreRoot, ["install", "--frozen-lockfile"]);
  await runPnpm(coreRoot, ["check"]);
} else {
  process.stdout.write(
    "Development Harness Core source repository is absent; verified the vendored package hash and installed identity.\n",
  );
}
await runPnpm(root, ["harness:typecheck"]);
await runPnpm(root, ["harness:test"]);
await runPnpm(root, ["harness", "--", "help"]);
process.stdout.write(
  `Development Harness ready: ${source.package}@${source.version} ${source.commit}\n`,
);

async function git(cwd, argv) {
  const result = await execFileAsync("git", argv, { cwd });
  return result.stdout.trim();
}

async function runPnpm(cwd, argv) {
  await new Promise((resolve, reject) => {
    const child = spawn(
      process.platform === "win32" ? "pnpm.cmd" : "pnpm",
      argv,
      { cwd, shell: false, stdio: "inherit" },
    );
    child.once("error", reject);
    child.once("close", (code) =>
      code === 0
        ? resolve()
        : reject(new Error(`pnpm ${argv.join(" ")} exited with ${code ?? 1}`)),
    );
  });
}
