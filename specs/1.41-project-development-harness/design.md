# 1.41 Project Development Harness Design

## Decision

KnoArbor composes the exact shared `@development-harness/core` used by itpc-x
with a repository-local Adapter. The previous Python control plane and method
bundle are deleted. No compatibility path selects between implementations.

```text
docs/standards + AGENTS.md
          |
          v
workflow classifier
  | Discovery / Direct lanes
  `-> admitted Patterned Harness
                |
                v
     @development-harness/core
                |
                v
       KnoArbor ProjectAdapter
       | paths / owners / Skills
       | capabilities / hosts
       | Gates / verification
       ` branch policy
```

## Source Reuse

`reference-reuse-manifest.json` is the bounded migration ledger. The core
runtime, pin/bootstrap pattern, Controller separation, four workflow lanes,
four-axis capability maturity, semantic responsibility projection, fixed Gate
catalog, and documentation lifecycle rules come from the reference project.

KnoArbor adapts owner resolution, commands, capability IDs, formal hosts,
public-upstream/private-downstream policy, and its flat public-doc layout.
Reference-specific product domains, Team Mode, TAPD/MCP, benchmark runtime,
Claude Code parity archive, and enterprise delivery are not copied.

## Composition Root

`harness/src/index.ts`:

1. rejects Patterned Harness admission whose delivery units do not span two
   owners;
2. verifies `harness/core-source.json`;
3. verifies the vendored package SHA-256 and installed package identity;
4. when the Core source repository is present, requires its exact clean commit
   and runs the producer check;
5. imports Core and passes the KnoArbor Adapter.

The root `pnpm harness --` command is the only current operator entry.

## Adapter

The Adapter implements Core's complete v3 contract:

- ignored state/archive roots under `.knoarbor/harness/`;
- project Rules and code/capability navigation;
- repository Skill lookup by exact metadata;
- explicit path-to-owner mapping with fixed owner commands;
- capability resolution from `docs/CAPABILITY_MAP.md`;
- semantic-host resolution from the validated JSON projection;
- fixed Gate catalog and verification roles;
- `codex/` branch policy.

Owner resolution is explicit rather than inferred from package manifests
because KnoArbor combines Python, npm subprojects, governance, and Harness
assets.

## Capability And Authority Model

The Capability Map stores stable IDs and four dimensions separately. The
Adapter parses exact eight-cell rows and maps only declared vocabulary.

`docs/CONTRACTS.md` owns formal host and responsibility declarations.
`harness/rules/semantic-hosts.json` is a machine projection with:

- stable host ID;
- exact code host;
- owner document;
- responsibility IDs classified as truth, lifecycle, recovery, coordination,
  or boundary publication.

Governance checks require every projected ID and code path in the Active
Contract and reject duplicate responsibility ownership. The projection does
not describe behavior and cannot become a second contract.

## Workflow Lanes

Classification precedes implementation:

1. Architecture Discovery for unknown facts.
2. Direct Maintenance for semantic-preserving upkeep.
3. Direct SDD for one frozen atomic semantic transaction.
4. Patterned Harness for established multi-owner product delivery with bounded
   authority decisions.

Harness self-maintenance is Bootstrap Maintenance because the replacing runtime
cannot produce independent evidence about itself.

## Skills

Four concise project Skills convert the standards into executable procedures:

- `development-workflow`;
- `development-harness-controller`;
- `documentation-curation-review`;
- `semantic-contract-review`.

Skills do not own stage state, approval state, product truth, Gate results, or
capability maturity. `agents/openai.yaml` contains only UI metadata.

## Gate Design

Universal hard Gates:

- Core scope check;
- `git diff --check`;
- Core secret scan;
- documentation governance.

Optional hard Gates cover changed lint, planned owner typecheck/test,
documentation links, architecture, broad Python tests, renderer typecheck, and
desktop typecheck. Core executes argv arrays without a shell, redacts output,
and compares stable baseline/acceptance identities.

## Documentation Model

The existing public flat layout remains stable. Governance assigns one class
and owner, defines Active/Supporting Contract admission, excludes mutable task
state, and enforces Keep/Update/Merge/Archive/Delete. External sources are
evidence classified in the owning spec, not a parallel documentation tree.

## Migration

1. Add standards, Skills, Adapter, Rules, pin, bootstrap, and current docs.
2. Convert capability maturity and formal-host projection.
3. Strengthen deterministic governance.
4. Delete the Python controller, its test, and method bundle.
5. Remove all current references to retired paths.
6. Install frozen dependencies and validate Core/Adapter.
7. Run a bounded temporary journey.
8. Merge public-first, then integrate the public commit into private
   `SieArbor`; private product Skills may extend these generic lanes but cannot
   fork them.

Rollback reverts the complete migration commit. The deleted Python runtime is
recoverable from Git but is not retained as an in-tree fallback.
