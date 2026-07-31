import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import {
  nodeProjectHost,
  resolveAdapterCapability,
  resolveAdapterSemanticHost,
  validateProjectAdapter,
} from "@development-harness/core";
import { knoarborProjectAdapter } from "./adapter.js";

const root = path.resolve(import.meta.dirname, "../../../..");

test("adapter declares the complete project contract", () => {
  assert.equal(knoarborProjectAdapter.manifest.project.id, "knoarbor");
  assert.equal(
    new Set(knoarborProjectAdapter.manifest.capabilities).size,
    knoarborProjectAdapter.manifest.capabilities.length,
  );
  assert.ok(
    knoarborProjectAdapter.manifest.verification.universalSafetyGateIds.includes(
      "documentation-check",
    ),
  );
});

test("Patterned Harness uses repository-local navigation and rules", () => {
  for (const relative of [
    knoarborProjectAdapter.manifest.paths.rulesFile,
    ...knoarborProjectAdapter.manifest.paths.navigation,
  ])
    assert.doesNotMatch(relative, /^(?:\/|[A-Za-z]:[\\/])/u);
});

test("adapter resolves current capability and semantic-host authorities", async () => {
  const adapter = await validateProjectAdapter(root, knoarborProjectAdapter);
  const capability = await resolveAdapterCapability(adapter, {
    projectRoot: root,
    capabilityId: "CAP-DEVELOPMENT-HARNESS",
    host: nodeProjectHost,
  });
  const semanticHost = await resolveAdapterSemanticHost(adapter, {
    projectRoot: root,
    semanticHostId: "HOST-QUERY-PIPELINE",
    host: nodeProjectHost,
  });
  const owners = await adapter.resolveOwners({
    projectRoot: root,
    paths: ["src/knoarbor/pipelines/query.py", "renderer/src/api/query.ts"],
    host: nodeProjectHost,
  });

  assert.equal(capability.ownerDocument, "specs/1.41-project-development-harness/requirements.md");
  assert.equal(semanticHost.hostModule, "src/knoarbor/pipelines/query.py");
  assert.deepEqual(
    (owners as Array<{ owner: string }>).map((item) => item.owner),
    ["python-runtime", "renderer"],
  );
});
