import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { knoarborProjectAdapter } from "./adapters/knoarbor/adapter.js";

export async function runHarnessCli(argv: readonly string[]) {
  await assertPatternedCoordination(argv);
  const runtime = await loadPinnedHarnessRuntime();
  return runtime.runHarnessCli([...argv], runtime.adapter);
}

export async function assertPatternedCoordination(argv: readonly string[]) {
  if (argv[0] !== "init") return;
  const flag = argv.indexOf("--admission");
  const admissionPath = argv[flag + 1];
  if (flag < 0 || !admissionPath) return;
  const admission = JSON.parse(await readFile(admissionPath, "utf8")) as {
    classification?: string;
    harnessNeed?: { deliveryUnits?: Array<{ ownerId?: string }> };
  };
  if (admission.classification !== "harness_initiative") return;
  const owners = new Set(
    (admission.harnessNeed?.deliveryUnits ?? [])
      .map((unit) => unit.ownerId?.trim())
      .filter((owner): owner is string => Boolean(owner)),
  );
  if (owners.size < 2)
    throw new Error(
      "Patterned Harness requires delivery units owned by at least two repository owners; use Direct SDD for one-owner work",
    );
}

export async function loadPinnedHarnessRuntime(
  projectRoot = path.resolve(import.meta.dirname, "../.."),
) {
  await assertPinnedHarnessCore(projectRoot);
  const core = await import("@development-harness/core");
  return { runHarnessCli: core.runHarnessCli, adapter: knoarborProjectAdapter };
}

async function assertPinnedHarnessCore(projectRoot: string) {
  const source = JSON.parse(
    await readFile(path.join(projectRoot, "harness/core-source.json"), "utf8"),
  ) as {
    schemaVersion: string;
    package: string;
    version: string;
    path: string;
    commit: string;
    artifact: string;
    artifactSha256: string;
  };
  if (
    source.schemaVersion !== "development_harness.core_source.v1" ||
    source.package !== "@development-harness/core" ||
    !/^\d+\.\d+\.\d+$/u.test(source.version) ||
    source.path !== "../development-harness" ||
    !/^[a-f0-9]{40}$/u.test(source.commit) ||
    source.artifact !==
      "harness/vendor/development-harness-core-0.11.0.tgz" ||
    !/^[a-f0-9]{64}$/u.test(source.artifactSha256)
  )
    throw new Error("harness/core-source.json is invalid");
  const artifact = await readFile(path.join(projectRoot, source.artifact));
  if (createHash("sha256").update(artifact).digest("hex") !== source.artifactSha256)
    throw new Error("Vendored Harness Core artifact differs from its source pin");
  const manifest = JSON.parse(
    await readFile(
      path.join(
        projectRoot,
        "harness/node_modules/@development-harness/core/package.json",
      ),
      "utf8",
    ),
  ) as { name?: string; version?: string };
  if (manifest.name !== source.package || manifest.version !== source.version)
    throw new Error("Installed Harness Core differs from the pinned artifact");
}
