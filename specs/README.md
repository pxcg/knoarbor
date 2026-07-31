# Specs

KnoArbor uses a lightweight spec-driven development workflow for changes that
affect architecture, public contracts, source connectors, semantic contracts,
workflow behavior, or release-critical user experience.

This directory works alongside the public documentation in `docs/`. Specs are
feature-level implementation artifacts that connect the roadmap to code,
tests, and release notes.

## Source Of Truth Map

| Concern | Source of truth |
| --- | --- |
| Product positioning and common usage | `README.md`, `README.zh-CN.md` |
| Long-term roadmap | `docs/ROADMAP.md`, `docs/zh/ROADMAP.md` |
| Cross-feature capability state | `docs/CAPABILITY_MAP.md`, `docs/zh/CAPABILITY_MAP.md` |
| Architecture layers and ownership | `docs/ARCHITECTURE.md`, `docs/zh/ARCHITECTURE.md` |
| Frozen cross-layer contracts | `docs/CONTRACTS.md`, `docs/UI_CONTRACT.md` |
| Durable architecture decisions | `docs/adr/*.md` |
| Knowledge atom ingest boundary | `docs/adr/0001-knowledge-atom-ingest.md`, `specs/1.26-raw-grounded-ingest-chain/`, `specs/1.27-deterministic-entity-identity/` |
| Maintainer process and governance | `docs/MAINTAINERS.md`, `docs/zh/MAINTAINERS.md` |
| Public API contract | `docs/API_COMPATIBILITY.md`, `docs/API.md`, `src/knoarbor/entrypoints/api_contract.py` |
| CLI contract | `docs/CLI.md`, `src/knoarbor/cli_commands/parser.py` |
| Config contract | `docs/CONFIGURATION.md`, `src/knoarbor/core/config.py` |
| Error contract | `docs/ERROR_CODES.md`, `src/knoarbor/core/errors.py` |
| Release decision | `docs/RELEASE_CHECKLIST.md`, `scripts/release-check.sh` |
| Feature-level requirements, design, tasks, and verification | `specs/<feature>/` |
| Spec lifecycle, owner domain, and successor chain | `specs/registry.json` |

`registry.json` is authoritative for whether a spec is Proposed, Accepted,
Implemented, Superseded, or Historical. The lists below are navigation views
and must not establish a second lifecycle policy.

## Active Roadmap Specs

| Roadmap line | Spec | Management focus |
| --- | --- | --- |
| 1.3.x | [Source Ecosystem](1.3-source-ecosystem/requirements.md) | Connector boundaries, source catalog, source settings schema, source preflight. |
| 1.4.x | [Machine Index Layer](1.4-machine-index-layer/requirements.md) | Retrieval provider contracts, local machine index, rebuild/freshness state. |
| 1.5.x | [Knowledge Governance](1.5-knowledge-governance/requirements.md) | Lint operation taxonomy, autonomous repair, review evidence, reports and diffs. |
| 1.6.x | [Productized Console](1.6-productized-console/requirements.md) | UI information architecture, loading strategy, report readability, component reuse. |
| 1.7.x | [CLI/API/Skill Closure](1.7-cli-api-skill-closure/requirements.md) | Public surface parity, response envelopes, skill operation maturity before 2.0. |
| 1.8.x | [Model Capability Probe](1.8-model-capability-probe/requirements.md) | Provider discovery, bounded probes, local-model capability detection, explicit config writes. |
| 1.9.x | [Vault Workspaces](1.9-vault-workspaces/requirements.md) | Vault registry, vault ID selection, multi-vault UX, workspace identity. |
| 1.10.x | [Wiki Chat Agent](1.10-wiki-chat-agent/requirements.md) | Console chat surface, answer synthesis, sessions, and `/chat` orchestration. Query evidence is owned by 1.38. |
| 1.11.x | [Chat Memory](1.11-chat-memory/requirements.md) | Vault-scoped chat preferences, memory recall, explicit memory capture, and memory audit events. |
| 1.21.x | [Vault Artifacts And AppData Boundary](1.21-vault-artifacts-and-appdata-boundary/requirements.md) | Single app-data install root, vault artifact boundaries, generated image storage, and backup semantics. |
| 1.26.x | [Raw-Grounded Ingest Chain](1.26-raw-grounded-ingest-chain/requirements.md) | Clean raw-first ingest stages, segment-level extraction, minimal locator metadata, deterministic projection, and diagnostics separation. |
| 1.27.x | [Deterministic Entity Identity](1.27-deterministic-entity-identity/requirements.md) | Stable entity contributions, identity resolution, and cross-source linking. |
| 1.37.x | [Local-First Ingest Simplification](1.37-local-first-ingest-simplification/requirements.md) | Local operation ownership, source-level recovery, one materialization epoch, and removal of persistent worker machinery. |
| 1.38.x | [Unified Active Raw Evidence Retrieval](1.38-semantic-indexed-raw-query/requirements.md) | Atom/claim and Raw-unit locator recall, unified active evidence identities, typed query outcomes, and raw-only factual context. |
| 1.39.x | [Codebase Modularity](1.39-codebase-modularity/requirements.md) | Backend dependency direction, responsibility boundaries, frontend domain organization, and maintainability gates. |
| 1.41.x | [Project Development Harness](1.41-project-development-harness/requirements.md) | Shared-Core Patterned Harness, project Adapter, workflow lanes, Skills, capability/host projections, and documentation governance; Direct Maintenance and Direct SDD remain first-class. |
| 1.42.x | [Public Product Line Convergence](1.42-public-product-line-convergence/requirements.md) | Public-safe capability convergence, canonical product identity, compatibility classification, and upstream/downstream governance. |

## Spec Lifecycle

Use a feature spec when a change introduces or significantly changes:

- a public API endpoint, CLI command, config field, report schema, or skill
  operation;
- a connector, source type, document preprocessing path, or source segmentation
  behavior;
- an architecture layer or cross-layer contract;
- a semantic prompt/schema contract;
- autonomous maintenance behavior, verification, or recovery behavior;
- a release theme with multiple linked tasks.

Small typo fixes, isolated UI copy changes, dependency patch bumps, and
single-file bug fixes can reference an existing spec or skip a dedicated spec.

## SDD Intensity

Choose the lightest SDD level that still keeps requirements, design, task
state, implementation, and verification aligned.

| Level | Applies to | Required record |
| --- | --- | --- |
| Full spec | Public contracts, architecture layers, source connectors, semantic contracts, workflow behavior, autonomous maintenance, durable reports, or release themes. | `specs/<feature>/{requirements,design,tasks,verification}.md` |
| Light spec | A focused extension inside an accepted boundary, such as a UI interaction refinement, a small connector setting, or an existing CLI/API parameter. | Existing feature spec task and verification update. |
| Patch record | Copy edits, focused bug fixes, tests for existing behavior, dependency patch bumps, or small type fixes. | Commit message and relevant test evidence. |
| ADR | A durable decision that is expensive to reverse, especially public API shape, vault semantics, model boundary, storage/index strategy, or extension model. | `docs/adr/NNNN-title.md`, linked from related specs or docs. |

Full specs and ADRs can be used together. The ADR records the durable decision;
the feature spec records implementation requirements, task state, and
verification.

## Lifecycle

- `Proposed`: under review and not authorized for implementation.
- `Accepted`: current owner with approved design and remaining work.
- `Implemented`: current owner whose required baseline is verified.
- `Superseded`: replaced by named successor specs and retained as history.
- `Historical`: useful context that owns no current implementation boundary.

Current lifecycle is read from `registry.json`. New specs are allowed only when
no current spec owns the affected contract. Historical gaps in numbering and
incomplete superseded spec shapes are preserved rather than filled with empty
documents.

## File Shape

Each feature spec keeps four core documents:

```text
specs/<feature>/
├── requirements.md
├── design.md
├── tasks.md
└── verification.md
```

- `requirements.md`: user goals, non-goals, scenarios, and acceptance criteria.
- `design.md`: owning layers, public contracts, internal contracts, data flow,
  and rejected alternatives.
- `tasks.md`: implementation tasks with status.
- `verification.md`: automated tests, manual checks, release gates, and known
  risks.

Focused boundary files such as `runtime-contract.md`, `schema-boundary.md`, or
`source-digest-boundary.md` are allowed when a feature owns a durable
cross-module contract. The core four documents remain the navigation entry.

When implementation evidence changes the design, update the spec before or in
the same commit as the code change.

## SDD Conformance Checklist

A change is considered aligned with KnoArbor's spec-driven development model
when the spec, code, tests, and docs agree on the same ownership boundary.

Before implementation:

- identify the roadmap line or feature spec that owns the change;
- update `requirements.md` when the user-facing goal, non-goal, or acceptance
  criteria changes;
- update `design.md` when layer ownership, data flow, public contracts, or
  rejected alternatives change;
- update `tasks.md` before or during implementation so task status reflects
  reality;
- update `verification.md` when the test gate or manual release check changes.

During implementation:

- place code in the owning architecture layer described by `design.md`;
- keep adapters thin: CLI, API, UI, and skills should call stable services or
  pipelines instead of reimplementing workflow policy;
- keep semantic agents narrow: prompts and schemas may describe decisions, but
  storage, checkpoints, retries, and reports belong to non-semantic layers;
- keep connector-specific behavior inside connectors or document processors;
- add broad fallbacks only when the spec names the trigger, owner, report
  surface, and verification check.

Before completion:

- run the verification commands listed in the feature spec or record why a
  listed check is outside the changed scope;
- promote stable user-facing behavior into `docs/` when the behavior is public;
- update release notes when the change is release-facing;
- leave the working implementation simpler than the spec: if the spec has
  obsolete rejected paths or stale task wording, clean it up before marking the
  feature complete.

## Engineering Rules

Feature specs must follow the project-wide rules in:

- `docs/ARCHITECTURE.md`
- `docs/MAINTAINERS.md`
- `docs/DEVELOPMENT.md`
- `docs/TESTING.md`

In particular:

- Prefer root-cause and architecture fixes over local fallback patches.
- Keep public contracts explicit and tested.
- Keep runtime vault data out of automated tests and release scripts.
- Keep connector-specific logic inside connectors, not semantic agents.
- Keep semantic agents narrow: prompt + schema + validation, not storage or
  lifecycle policy.
## Ingest Runtime Owner

[1.37 Local-First Ingest Simplification](1.37-local-first-ingest-simplification/design.md)
is the implemented owner for local ingest execution, recovery, factual
publication, and materialization. Intermediate designs 1.28 through 1.36 were
retired after their durable conclusions moved into 1.37 and ADR 0004.
