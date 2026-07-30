import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  WIN_CODE_SIGN_SHA256,
  archiveSha256,
  builderInvocation,
  cachePaths,
  extractionArguments,
  isPreparedCache,
} from "../scripts/run-windows-builder.mjs";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const desktopRequire = createRequire(resolve(desktopRoot, "package.json"));
const desktopManifest = desktopRequire("./package.json");

test("Windows cache preparation declares its 7-Zip runtime directly", () => {
  assert.equal(desktopManifest.devDependencies["7zip-bin"], "5.2.0");
  assert.equal(desktopManifest.dependencies?.["7zip-bin"], undefined);
  assert.match(desktopRequire.resolve("7zip-bin"), /7zip-bin[\\/]index\.js$/);
});

test("desktop manifest does not retain the unused preload toolkit", () => {
  assert.equal(desktopManifest.dependencies?.["@electron-toolkit/preload"], undefined);
  assert.equal(desktopManifest.devDependencies?.["@electron-toolkit/preload"], undefined);
});

test("icon verification reads the electron-builder configuration", () => {
  const result = spawnSync(process.execPath, [resolve(desktopRoot, "scripts/verify-icon-assets.mjs")], {
    cwd: desktopRoot,
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Verified KnoArbor Windows icon assets/);
});

test("electron-builder runs through its JavaScript CLI without a Windows cmd wrapper", () => {
  const invocation = builderInvocation("nsis", desktopRoot);
  assert.equal(invocation.command, process.execPath);
  assert.equal(invocation.args[0], resolve(desktopRoot, "node_modules/electron-builder/cli.js"));
  assert.deepEqual(invocation.args.slice(1), [
    "--config",
    "electron-builder.config.cjs",
    "--win",
    "nsis",
    "--publish",
    "never",
  ]);
});

test("winCodeSign extraction excludes the complete macOS subtree", () => {
  assert.deepEqual(extractionArguments("archive.7z", "output"), [
    "x",
    "-bd",
    "-y",
    "archive.7z",
    "-ooutput",
    "-xr!darwin",
  ]);
});

test("archive digest is deterministic", () => {
  assert.equal(
    archiveSha256(Buffer.from("KnoArbor")),
    "30442835a90d86154cb8ce92e3b789c7ac7fde40ba461e0d2564252fd151924e",
  );
});

test("prepared cache requires Windows tools, the pinned marker, and no darwin directory", async () => {
  const root = await mkdtemp(join(tmpdir(), "knoarbor-wincodesign-test-"));
  const paths = cachePaths(root);
  try {
    await mkdir(join(paths.target, "windows-10", "x64"), { recursive: true });
    await writeFile(join(paths.target, "rcedit-x64.exe"), "fixture");
    await writeFile(join(paths.target, "windows-10", "x64", "signtool.exe"), "fixture");
    await writeFile(paths.marker, `${WIN_CODE_SIGN_SHA256}\n`);
    assert.equal(await isPreparedCache(paths), true);

    await mkdir(join(paths.target, "darwin"));
    assert.equal(await isPreparedCache(paths), false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
