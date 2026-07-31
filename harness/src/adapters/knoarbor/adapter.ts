import path from "node:path";
import { z } from "zod";
import {
  PROJECT_ADAPTER_SCHEMA_VERSION,
  resolveInside,
  type ProjectAdapter,
} from "@development-harness/core";
import { GATES } from "./gates.js";

export const knoarborProjectAdapter: ProjectAdapter = {
  manifest: {
    schemaVersion: PROJECT_ADAPTER_SCHEMA_VERSION,
    capabilities: [
      "state",
      "archive",
      "navigation",
      "skills",
      "owners",
      "gates",
      "verification",
      "git_delivery",
      "capability_traceability",
      "semantic_hosting",
    ],
    project: { id: "knoarbor", displayName: "KnoArbor" },
    paths: {
      stateRoot: ".knoarbor/harness/initiatives",
      archiveRoot: ".knoarbor/harness/archive",
      rulesFile: "harness/rules/project-rules.json",
      navigation: [
        "docs/standards/code-navigation-map.md",
        "docs/CAPABILITY_MAP.md",
      ],
      skillRoots: [".codex/skills"],
    },
    gates: Object.entries(GATES).map(([id, gate]) => ({
      id,
      command: [...gate.command],
      enforcement: gate.enforcement,
      stages: [...gate.stages],
      required: gate.required,
    })),
    verification: {
      universalSafetyGateIds: [
        "scope-check",
        "diff-check",
        "secret-scan",
        "documentation-check",
      ],
      scopeCheckGateId: "scope-check",
      changedLintGateId: "changed-lint",
      secretScanGateId: "secret-scan",
      plannedTypecheckGateId: "planned-typecheck",
      plannedTestGateId: "planned-test",
      broadTestGateIds: ["python-tests"],
      changedLintCommandPrefix: ["uv", "run", "--extra", "dev", "ruff", "check"],
    },
    git: { branchPrefix: "codex/" },
  },

  async resolveSkill({ projectRoot, skillId, host }) {
    if (!/^[a-z0-9][a-z0-9-]*$/u.test(skillId))
      throw new Error(`invalid Skill ID: ${skillId}`);
    const file = `.codex/skills/${skillId}/SKILL.md`;
    const absolute = resolveInside(projectRoot, file);
    if (!(await host.isFile(absolute)))
      throw new Error(`unknown project Skill: ${skillId}`);
    const content = await host.readFile(absolute, "utf8");
    const name = /^name:\s*["']?([^"'\r\n]+)["']?\s*$/mu.exec(content)?.[1];
    if (!name) throw new Error(`Skill metadata name is missing: ${skillId}`);
    return { id: skillId, name: name.trim(), file };
  },

  async resolveOwners({ paths }) {
    const owners = new Map<string, ReturnType<typeof ownerForPath>>();
    for (const relative of [...new Set(paths)].sort()) {
      const owner = ownerForPath(relative);
      owners.set(owner.owner, owner);
    }
    return [...owners.values()].sort((left, right) =>
      left.owner.localeCompare(right.owner),
    );
  },

  async resolveCapability({ projectRoot, capabilityId, host }) {
    const file = "docs/CAPABILITY_MAP.md";
    const content = await host.readFile(resolveInside(projectRoot, file), "utf8");
    const row = content
      .split("\n")
      .find((line) => line.startsWith(`| ${capabilityId} |`));
    if (!row) throw new Error(`unknown KnoArbor Capability: ${capabilityId}`);
    const cells = row
      .split("|")
      .slice(1, -1)
      .map((cell) => cell.trim());
    if (cells.length !== 8)
      throw new Error(`invalid KnoArbor Capability row: ${capabilityId}`);
    const ownerDocument = cells[7]?.match(/^`([^`]+\.md)`$/u)?.[1];
    if (!ownerDocument)
      throw new Error(`invalid Capability owner: ${capabilityId}`);
    return {
      id: capabilityId,
      name: cells[1],
      ownerDocument,
      maturity: {
        contract: maturity(
          cells[2],
          ["frozen", "defined", "undefined"] as const,
          capabilityId,
        ),
        implementation: maturity(
          cells[3],
          ["complete", "foundation", "partial", "unimplemented"] as const,
          capabilityId,
        ),
        automatedEvidence: maturity(
          cells[4],
          ["broad", "focused", "mapped", "none"] as const,
          capabilityId,
        ),
        productAcceptance: maturity(
          cells[5],
          ["scoped_pass", "partial", "pending", "not_applicable"] as const,
          capabilityId,
        ),
      },
    };
  },

  async resolveSemanticHost({ projectRoot, semanticHostId, host }) {
    const file = "harness/rules/semantic-hosts.json";
    const registry = SemanticHostRegistrySchema.parse(
      JSON.parse(await host.readFile(resolveInside(projectRoot, file), "utf8")),
    );
    const binding = registry.hosts.find(
      (candidate) => candidate.id === semanticHostId,
    );
    if (!binding)
      throw new Error(`unknown KnoArbor semantic host: ${semanticHostId}`);
    return binding;
  },
};

function ownerForPath(relative: string) {
  if (relative.startsWith("src/knoarbor/"))
    return owner(
      "python-runtime",
      "src/knoarbor",
      ["uv", "run", "--extra", "dev", "ruff", "check", "src", "tests"],
      ["uv", "run", "python", "-m", "unittest", "discover", "-s", "tests"],
    );
  if (relative.startsWith("renderer/"))
    return owner(
      "renderer",
      "renderer",
      ["npm", "--prefix", "renderer", "run", "typecheck"],
      ["npm", "--prefix", "renderer", "run", "test:e2e"],
    );
  if (relative.startsWith("desktop/"))
    return owner(
      "desktop",
      "desktop",
      ["npm", "--prefix", "desktop", "run", "typecheck"],
      ["npm", "--prefix", "desktop", "test"],
    );
  if (
    relative.startsWith("harness/") ||
    relative.startsWith(".codex/skills/")
  )
    return owner(
      "development-harness",
      ".",
      ["pnpm", "--filter", "@knoarbor/development-harness", "typecheck"],
      ["pnpm", "--filter", "@knoarbor/development-harness", "test"],
    );
  if (relative.startsWith("scripts/"))
    return owner(
      "maintainer-automation",
      "scripts",
      ["uv", "run", "--extra", "dev", "ruff", "check", "scripts"],
      ["uv", "run", "python", "-m", "unittest", "discover", "-s", "tests"],
    );
  if (relative.startsWith("docs/") || relative.startsWith("specs/"))
    return owner(
      "documentation-governance",
      ".",
      undefined,
      ["uv", "run", "python", "scripts/check-doc-governance.py"],
    );
  return owner(
    "repository-governance",
    ".",
    undefined,
    ["uv", "run", "python", "scripts/check-doc-governance.py"],
  );
}

function owner(
  name: string,
  root: string,
  typecheck?: string[],
  test?: string[],
) {
  return {
    owner: name,
    root,
    commands: {
      ...(typecheck ? { typecheck } : {}),
      ...(test ? { test } : {}),
    },
  };
}

function maturity<const T extends readonly string[]>(
  value: string | undefined,
  allowed: T,
  capabilityId: string,
): T[number] {
  if (!value || !allowed.includes(value))
    throw new Error(`invalid maturity for ${capabilityId}: ${value ?? "<missing>"}`);
  return value as T[number];
}

const SemanticHostRegistrySchema = z
  .object({
    schemaVersion: z.literal("knoarbor.semantic_hosts.v1"),
    authority: z.literal("projection_of_active_contracts"),
    hosts: z.array(
      z
        .object({
          id: z.string().regex(/^HOST-[A-Z0-9]+(?:-[A-Z0-9]+)*$/u),
          name: z.string().min(1),
          hostModule: z.string().min(1),
          ownerDocument: z.string().min(1),
          responsibilities: z.array(
            z
              .object({
                id: z.string().regex(/^RESP-[A-Z0-9]+(?:-[A-Z0-9]+)*$/u),
                kind: z.enum([
                  "truth",
                  "lifecycle",
                  "recovery",
                  "coordination",
                  "boundary_publication",
                ]),
              })
              .strict(),
          ),
        })
        .strict(),
    ),
  })
  .strict()
  .superRefine((registry, context) => {
    const hostIds = registry.hosts.map((host) => host.id);
    if (new Set(hostIds).size !== hostIds.length)
      context.addIssue({ code: z.ZodIssueCode.custom, message: "duplicate host ID" });
    const responsibilities = registry.hosts.flatMap((host) =>
      host.responsibilities.map((item) => item.id),
    );
    if (new Set(responsibilities).size !== responsibilities.length)
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "semantic responsibility has multiple hosts",
      });
  });
