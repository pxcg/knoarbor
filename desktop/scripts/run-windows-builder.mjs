import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

export const WIN_CODE_SIGN_VERSION = "2.6.0";
export const WIN_CODE_SIGN_SHA256 =
  "cdaec7154dda7cc31f88d886e2489379a0625a737d610b5ae7f62a12f16743a4";
export const WIN_CODE_SIGN_URL =
  `https://github.com/electron-userland/electron-builder-binaries/releases/download/` +
  `winCodeSign-${WIN_CODE_SIGN_VERSION}/winCodeSign-${WIN_CODE_SIGN_VERSION}.7z`;

const scriptPath = fileURLToPath(import.meta.url);
const desktopRoot = resolve(dirname(scriptPath), "..");
const require = createRequire(import.meta.url);

export function cachePaths(root = resolve(desktopRoot, ".cache/electron-builder")) {
  const parent = join(root, "winCodeSign");
  const target = join(parent, `winCodeSign-${WIN_CODE_SIGN_VERSION}`);
  return {
    root,
    parent,
    target,
    marker: join(target, ".knoarbor-windows-cache"),
  };
}

export function archiveSha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

export function extractionArguments(archive, output) {
  return ["x", "-bd", "-y", archive, `-o${output}`, "-xr!darwin"];
}

export function builderInvocation(target, root = desktopRoot) {
  return {
    command: process.execPath,
    args: [
      resolve(root, "node_modules/electron-builder/cli.js"),
      "--config",
      "electron-builder.config.cjs",
      "--win",
      target,
      "--publish",
      "never",
    ],
  };
}

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export async function isPreparedCache(paths) {
  if (
    !(await exists(paths.marker)) ||
    !(await exists(join(paths.target, "rcedit-x64.exe"))) ||
    !(await exists(join(paths.target, "windows-10", "x64", "signtool.exe"))) ||
    (await exists(join(paths.target, "darwin")))
  ) {
    return false;
  }
  return (await readFile(paths.marker, "utf8")).trim() === WIN_CODE_SIGN_SHA256;
}

function run(command, args, options = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, args, { stdio: "inherit", ...options });
    child.once("error", rejectRun);
    child.once("exit", (code, signal) => {
      if (code === 0) {
        resolveRun();
        return;
      }
      rejectRun(
        new Error(
          `${command} failed${signal ? ` with signal ${signal}` : ` with exit code ${code}`}`,
        ),
      );
    });
  });
}

async function downloadArchive(destination) {
  const response = await fetch(WIN_CODE_SIGN_URL, { redirect: "follow" });
  if (!response.ok) {
    throw new Error(`Unable to download winCodeSign: HTTP ${response.status}`);
  }
  const content = Buffer.from(await response.arrayBuffer());
  const digest = archiveSha256(content);
  if (digest !== WIN_CODE_SIGN_SHA256) {
    throw new Error(
      `winCodeSign checksum mismatch: expected ${WIN_CODE_SIGN_SHA256}, received ${digest}`,
    );
  }
  await writeFile(destination, content);
}

export async function prepareWindowsCodeSignCache(
  paths = cachePaths(process.env.ELECTRON_BUILDER_CACHE || undefined),
) {
  if (await isPreparedCache(paths)) {
    process.stdout.write(`Using prepared winCodeSign cache: ${paths.target}\n`);
    return paths;
  }

  await mkdir(paths.parent, { recursive: true });
  const stagingRoot = await mkdtemp(join(paths.parent, ".prepare-"));
  const archive = join(stagingRoot, `winCodeSign-${WIN_CODE_SIGN_VERSION}.7z`);
  const extracted = join(stagingRoot, "extracted");
  try {
    await downloadArchive(archive);
    const { path7za } = require("7zip-bin");
    await run(path7za, extractionArguments(archive, extracted));
    const stagedPaths = {
      ...paths,
      target: extracted,
      marker: join(extracted, ".knoarbor-windows-cache"),
    };
    await writeFile(stagedPaths.marker, `${WIN_CODE_SIGN_SHA256}\n`, "utf8");
    if (!(await isPreparedCache(stagedPaths))) {
      throw new Error("Prepared winCodeSign cache is incomplete or contains macOS assets");
    }
    await rm(paths.target, { recursive: true, force: true });
    await rename(extracted, paths.target);
  } finally {
    await rm(stagingRoot, { recursive: true, force: true });
  }
  return paths;
}

async function main() {
  const target = process.argv[2];
  if (!new Set(["dir", "nsis"]).has(target)) {
    throw new Error("Expected Windows target: dir or nsis");
  }

  const env = {
    ...process.env,
    ...(target === "dir" ? { CSC_IDENTITY_AUTO_DISCOVERY: "false" } : {}),
  };
  if (process.platform === "win32") {
    const paths = cachePaths();
    await prepareWindowsCodeSignCache(paths);
    env.ELECTRON_BUILDER_CACHE = paths.root;
  }
  const invocation = builderInvocation(target);
  await run(invocation.command, invocation.args, { cwd: desktopRoot, env });
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}

