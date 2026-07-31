---
name: development-workflow
description: Classify and deliver bounded KnoArbor repository work through Architecture Discovery, Direct Maintenance, Direct SDD, or Patterned Harness. Use for product changes, bug fixes, refactors, documentation governance, tests, release tooling, or reference adaptation before implementation; do not use it to operate an already admitted Harness Initiative.
---

# Development Workflow

Read `docs/standards/development-workflow.md`,
`docs/standards/spec-driven-development.md`, the owning stable contract, and
current Git state.

## Classify

Choose exactly one lane:

- Architecture Discovery when owner, authority, trust, lifecycle, recovery,
  migration, or product-path facts remain unknown.
- Direct Maintenance only when observable product/runtime semantics do not
  change.
- Direct SDD when the outcome, formal host, complete atomic write set,
  exclusions, negative oracle, rollback, and verification are frozen.
- Patterned Harness only for an established product pattern with bounded human
  decisions and at least two repository owners sharing one acceptance boundary.

Treat Harness Core, Controller, Adapter, Gate, method-state, and bootstrap
changes as Bootstrap Maintenance. Do not let the runtime under replacement
certify itself.

## Freeze

Bind the request, Git base, existing dirty work, outcome, exclusions, owning
spec/contract, formal host, authority chain, consumers, exact write set,
retired paths, negative oracle, rollback, and focused/affected commands.
Preserve unrelated changes.

## Execute

Update the smallest SDD owner before implementation. Change the complete atomic
set at formal hosts, remove superseded paths, run focused checks and one
affected closure, and update long-term docs only for delivered stable facts.
Return to Discovery if a new fact category appears.

## Review And Close

Obtain a read-only review ordered by:
`belongs -> authority -> contract -> behavior`.

Return the lane, goal, exclusions, owner, changed/retired paths, actual commands
and results, negative oracle, review verdict, exact branch/base/HEAD/worktree,
controlled transitions, blockers, frozen judgments, and next valid entry.
