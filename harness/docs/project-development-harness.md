# KnoArbor Development Harness

KnoArbor composes the product-neutral `@development-harness/core` with a small
repository Adapter. It does not maintain a second workflow runtime.

## Ownership

- Harness Core owns the fixed thirteen-stage lifecycle, schemas, artifact
  integrity, role relay, Gate orchestration, rollback, metrics, and closure.
- `harness/src/adapters/knoarbor/` owns KnoArbor paths, owners, Gates,
  capability and semantic-host projections.
- `.codex/skills/` owns on-demand operating procedures.
- `docs/standards/` owns lane classification and SDD rules.
- spec 1.41 owns the accepted repository-development control-plane contract.
- product tests and release scripts remain the authorities for behavior.

## Setup

The Core source commit and the exact vendored package hash are pinned by
`harness/core-source.json`. A normal clone installs the vendored package. When
the source repository is also present beside KnoArbor, bootstrap additionally
requires its exact clean commit and runs its complete producer checks.

```bash
pnpm harness:bootstrap
```

The bootstrap verifies package hash and installed identity, installs frozen
dependencies, runs available Core source checks, validates the Adapter, and
invokes the CLI.
Use `pnpm harness:bootstrap:check` for a non-installing verification.

## Use

Classify work first. Only admitted Patterned Harness work uses:

```bash
pnpm harness -- help
```

Direct Maintenance and Direct SDD use the `development-workflow` Skill without
creating Initiative state. Architecture Discovery freezes unknown facts before
either implementation lane.

Generated state lives under `.knoarbor/harness/` and is ignored by Git. Durable
conclusions return to specs, stable docs, tests, and Git; stage narration does
not.

## Upgrade

Upgrade Core by reviewing its release, updating the exact version/commit pin,
running bootstrap and a temporary-repository journey, then updating spec 1.41
only for changed contracts. Never edit a pinned Core worktree in place or keep
the retired Python controller as a fallback.
