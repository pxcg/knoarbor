# Specs

KnoArbor uses a lightweight spec-driven development workflow for changes that
affect architecture, public contracts, source connectors, semantic contracts,
workflow behavior, or release-critical user experience.

This directory does not replace the public documentation in `docs/`. Specs are
feature-level implementation artifacts that connect the roadmap to code,
tests, and release notes.

## Source Of Truth Map

| Concern | Source of truth |
| --- | --- |
| Product positioning and common usage | `README.md`, `README.zh-CN.md` |
| Long-term roadmap | `docs/ROADMAP.md`, `docs/zh/ROADMAP.md` |
| Architecture layers and ownership | `docs/ARCHITECTURE.md`, `docs/zh/ARCHITECTURE.md` |
| Maintainer process and governance | `docs/MAINTAINERS.md`, `docs/zh/MAINTAINERS.md` |
| Public API contract | `docs/API.md`, `src/knoarbor/entrypoints/api_contract.py` |
| CLI contract | `docs/CLI.md`, `src/knoarbor/cli_commands/parser.py` |
| Config contract | `docs/CONFIGURATION.md`, `src/knoarbor/core/config.py` |
| Error contract | `docs/ERROR_CODES.md`, `src/knoarbor/core/errors.py` |
| Release decision | `docs/RELEASE_CHECKLIST.md`, `scripts/release-check.sh` |
| Feature-level requirements, design, tasks, and verification | `specs/<feature>/` |

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
