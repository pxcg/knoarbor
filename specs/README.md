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
| Durable architecture decisions | `docs/adr/*.md` |
| Maintainer process and governance | `docs/MAINTAINERS.md`, `docs/zh/MAINTAINERS.md` |
| Public API contract | `docs/API.md`, `src/knoarbor/entrypoints/api_contract.py` |
| CLI contract | `docs/CLI.md`, `src/knoarbor/cli_commands/parser.py` |
| Config contract | `docs/CONFIGURATION.md`, `src/knoarbor/core/config.py` |
| Error contract | `docs/ERROR_CODES.md`, `src/knoarbor/core/errors.py` |
| Release decision | `docs/RELEASE_CHECKLIST.md`, `scripts/release-check.sh` |
| Feature-level requirements, design, tasks, and verification | `specs/<feature>/` |

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
| 1.10.x | [Wiki Chat Agent](1.10-wiki-chat-agent/requirements.md) | Console chat surface, page-first evidence retrieval, answer synthesis, and `/chat` contract. |
| 1.11.x | [Chat Memory](1.11-chat-memory/requirements.md) | Vault-scoped chat preferences, memory recall, explicit memory capture, and memory audit events. |
| 1.12.x | [Answer Set Selection](1.12-answer-set-selection/requirements.md) | Page-level primary/supporting/source selection, rejected candidates, and evidence-set quality. |

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

## File Shape

Each feature spec should keep four short documents:

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
