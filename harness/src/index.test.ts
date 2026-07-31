import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { assertPatternedCoordination } from "./index.js";

test("single-owner Patterned Harness admission routes to Direct SDD", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "knoarbor-admission-"));
  const admission = path.join(directory, "admission.json");
  await writeFile(
    admission,
    JSON.stringify({
      classification: "harness_initiative",
      harnessNeed: {
        deliveryUnits: [
          { ownerId: "python-runtime" },
          { ownerId: "python-runtime" },
        ],
      },
    }),
  );

  await assert.rejects(
    assertPatternedCoordination(["init", "--admission", admission]),
    /requires delivery units owned by at least two repository owners/u,
  );
  await rm(directory, { recursive: true });
});

test("multi-owner Patterned Harness admission passes composition preflight", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "knoarbor-admission-"));
  const admission = path.join(directory, "admission.json");
  await writeFile(
    admission,
    JSON.stringify({
      classification: "harness_initiative",
      harnessNeed: {
        deliveryUnits: [
          { ownerId: "python-runtime" },
          { ownerId: "renderer" },
        ],
      },
    }),
  );

  await assert.doesNotReject(
    assertPatternedCoordination(["init", "--admission", admission]),
  );
  await rm(directory, { recursive: true });
});
