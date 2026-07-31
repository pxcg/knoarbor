import { z } from "zod";

interface GateDefinition {
  command: readonly string[];
  enforcement: "hard" | "soft";
  stages: readonly (8 | 10 | 12)[];
  required: boolean;
}

export const GATES = {
  "scope-check": {
    command: ["harness", "scope-check"],
    enforcement: "hard",
    stages: [10, 12],
    required: true,
  },
  "diff-check": {
    command: ["git", "diff", "--check"],
    enforcement: "hard",
    stages: [8, 10, 12],
    required: true,
  },
  "secret-scan": {
    command: ["harness", "secret-scan"],
    enforcement: "hard",
    stages: [10, 12],
    required: true,
  },
  "changed-lint": {
    command: ["harness", "changed-lint"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
  "planned-typecheck": {
    command: ["harness", "planned-typecheck"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
  "planned-test": {
    command: ["harness", "planned-test"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
  "documentation-check": {
    command: ["uv", "run", "python", "scripts/check-doc-governance.py"],
    enforcement: "hard",
    stages: [10, 12],
    required: true,
  },
  "documentation-links": {
    command: ["uv", "run", "python", "scripts/check-doc-links.py"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
  "architecture-check": {
    command: ["uv", "run", "python", "scripts/check-architecture.py"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
  "python-tests": {
    command: ["uv", "run", "python", "-m", "unittest", "discover", "-s", "tests"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
  "renderer-typecheck": {
    command: ["npm", "--prefix", "renderer", "run", "typecheck"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
  "desktop-typecheck": {
    command: ["npm", "--prefix", "desktop", "run", "typecheck"],
    enforcement: "hard",
    stages: [10, 12],
    required: false,
  },
} as const satisfies Record<string, GateDefinition>;

export type GateId = keyof typeof GATES;
export const GateIdSchema = z.enum(
  Object.keys(GATES) as [GateId, ...GateId[]],
);
