# Maintainer Guide

This guide is for long-term KnoArbor maintainers. It complements
[Development](DEVELOPMENT.md), [Architecture](ARCHITECTURE.md), and
[Release Preflight Checklist](RELEASE_CHECKLIST.md).

The goal is to keep feature growth disciplined: new capabilities should enter
the project through clear layers, stable contracts, tests, and user-visible
documentation rather than ad hoc patches.

## Documentation Ownership

Use this map when deciding where a change belongs:

| Document | Owns | Should not contain |
| --- | --- | --- |
| `README.md` / `README.zh-CN.md` | Project positioning, screenshots, install path, common usage | Internal planning, implementation debates, private roadmap details |
| `docs/QUICKSTART.md` | First successful run | Full architecture or every CLI option |
| `docs/CONFIGURATION.md` | Config schema, provider setup, connector settings, privacy settings | Release process or code layout |
| `docs/CLI.md` | Public command-line behavior | Internal helper commands unless they are intentionally exposed |
| `docs/API.md` | Public HTTP API contracts | `/ui/api/*` internals or prototype endpoints |
| `docs/ARCHITECTURE.md` | Stable layers, workflow boundaries, module responsibilities | Short-term task lists or unresolved design debates |
| `docs/PROVENANCE_DESIGN.md` | Source-chain semantics and evidence model | General ingest/lint implementation details |
| `docs/TESTING.md` | Quality gates and test boundaries | Release checklist prose duplicated verbatim |
| `docs/RELEASE_CHECKLIST.md` | Release decision checklist | Feature roadmap |
| `docs/ROADMAP.md` | Direction from 1.0 to 2.0 | Per-commit changelog or sprint task list |
| `docs/MAINTAINERS.md` | Maintenance rules and long-term governance | User onboarding instructions |
| `specs/<feature>/*` | Feature-level requirements, design, task status, and verification plan | Stable user docs, release notes, or private design debates unrelated to the feature |
| `CHANGELOG.md` and `docs/releases/*` | Version-specific changes | Future planning |

When a feature changes behavior, update the smallest set of documents that own
that behavior. Avoid copying the same explanation into many files; link to the
source-of-truth document instead.

## Spec-Driven Development

KnoArbor uses lightweight spec-driven development for changes that affect
architecture, public contracts, source connectors, semantic contracts,
workflow behavior, or release-critical user experience.

Specs live in [`specs/`](../specs/README.md). They connect roadmap themes to
implementation, tests, and release notes. They do not replace long-term public
documentation:

- `docs/ROADMAP.md` owns product direction and version themes.
- `docs/ARCHITECTURE.md` owns stable layer boundaries.
- `docs/API.md`, `docs/CLI.md`, and `docs/CONFIGURATION.md` own public
  contracts.
- `specs/<feature>/` owns the feature-level requirement, design, task, and
  verification record.

Create or update a feature spec when a change introduces or significantly
changes:

- public API endpoints, CLI commands, config fields, report schemas, or skill
  operations;
- source connectors, source types, document preprocessing, or source
  segmentation behavior;
- architecture layers or cross-layer contracts;
- semantic prompt/schema contracts;
- autonomous maintenance, verification, retry, or recovery behavior.

Small typo fixes, isolated UI copy changes, dependency patch bumps, and
single-file bug fixes can reference an existing spec or skip a dedicated spec.

Implementation rule: when code reveals that the planned design is wrong,
update the spec in the same change rather than adding a local workaround. The
spec should explain the accepted design and rejected alternatives clearly
enough that future maintainers do not need to reconstruct the discussion from
commit history.

## Branch Discipline

Follow the branch model in [Development](DEVELOPMENT.md#branch-and-release-model).

In short:

- daily work starts from `dev`;
- focused work uses `feature/*`, `fix/*`, or `docs/*`;
- release tags are created from `main` only;
- urgent hotfixes may branch from `main`, then must be merged back into `dev`;
- public release tags should not be rewritten after users have consumed them.

If a change is committed directly to `main` for documentation or release
metadata, merge `main` back into `dev` before continuing feature work.

## Architecture Change Process

Before adding or moving a capability, identify the owning layer:

- **Source layer**: connectors, document preprocessing, source normalization.
- **Knowledge layer**: page types, vault paths, source digests, page rendering.
- **Index layer**: human index and machine retrieval indexes.
- **Governance layer**: lint, review, maintenance operations, verification.
- **Runtime layer**: queue, monitor, logs, locks, lifecycle reports.
- **Semantic layer**: prompt contracts, model gateway, validated schemas.
- **Adapter layer**: CLI, API, UI, npm launcher, skills.

Add new behavior where ownership is strongest. Do not compensate across layers.
For example, API routes should not repair malformed semantic output, and prompt
contracts should not own file-lock or checkpoint policy.

Architecture changes should normally include:

1. a short design decision in the commit message or PR description;
2. tests at the owning layer;
3. updates to `ARCHITECTURE.md` when boundaries move;
4. updates to CLI/API/config docs when public contracts change.

## Fallback And Retry Policy

KnoArbor prefers explicit reliability mechanisms over broad fallbacks.

Acceptable reliability mechanisms:

- retryable model/provider failures through the model gateway;
- structured-output retry inside the semantic runner;
- explicit run recovery through run metadata and checkpoints;
- file locks around local vault mutation;
- deterministic validation before and after page writes;
- user-visible failure reports for failed ingest/lint runs.

Avoid:

- silent fallback from one source path to another;
- swallowing malformed model output and inventing replacement content;
- writing partial pages after a failed source batch;
- retrying deterministic config, path, or policy errors;
- adding UI-only state that disagrees with CLI/API state.

If a fallback is necessary, document the trigger, the owner, the report surface,
and the test that proves it is bounded.

## Data Safety Rules

The runtime vault is user data. Automated tests and release scripts must use
temporary directories.

Never let automated gates write to:

- project-root `wiki/`;
- project-root `config.yaml`;
- project-root `.env`;
- private connector source directories;
- maintainer-local planning folders.

Use `mktemp -d` or the equivalent test fixture for any command that writes a
vault, config, report, ledger, checkpoint, or generated page.

## Compatibility Rules

Public contracts:

- CLI commands documented in `docs/CLI.md`;
- HTTP routes documented in `docs/API.md`;
- config fields documented in `docs/CONFIGURATION.md`;
- vault page semantics documented in `docs/CONCEPTS.md` and
  `docs/PROVENANCE_DESIGN.md`;
- error codes documented in `docs/ERROR_CODES.md`.

Internal contracts:

- `/ui/api/*` routes;
- semantic prompt internals;
- private service methods;
- UI component structure;
- maintainer scripts not listed in public docs.

When changing public contracts, update docs and tests in the same change. When
changing internal contracts, keep the public adapter behavior stable.

## Release Readiness

Before tagging a release:

1. run the normal development gate;
2. run release readiness checks;
3. run clean-clone smoke checks;
4. run live-model smoke when provider access is available;
5. review privacy and tracked-file boundaries;
6. update release notes and changelog;
7. tag only from `main`.

The release decision should be based on
[Release Preflight Checklist](RELEASE_CHECKLIST.md), not on local intuition.

## Long-Term Roadmap Hygiene

Roadmap items should describe stable product outcomes, not implementation
chores. Keep detailed implementation notes in issues, PRs, or local maintainer
notes outside the public release tree.

When a roadmap item is completed, update [Roadmap](ROADMAP.md) only if the
public direction changed. Do not turn the roadmap into a changelog.
