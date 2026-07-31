# 1.41 Project Development Harness Requirements

## Lifecycle And Ownership

Accepted. This specification owns KnoArbor's repository-development control
plane: workflow classification, Patterned Harness admission, project Adapter,
Gate catalog, capability/semantic-host projections, reusable Skills, bootstrap,
and adoption evidence.

Neighboring owners:

- `@development-harness/core` owns the product-neutral fixed workflow,
  schemas, state integrity, role relay, Gate orchestration, rollback, metrics,
  delivery protocol, and closure;
- feature specs own product requirements/design/tasks/verification;
- stable docs own current product and engineering contracts;
- repository tests/release scripts own the product checks they execute;
- Git/PR/release records own delivery.

No shipped KnoArbor runtime imports the Development Harness.

## Problem

The previous repository-local Python controller implemented a broad state
machine but duplicated the product-neutral Core later extracted and hardened by
the reference project. It also required Python 3.11 while exposing a generic
`python3` operator entry, so the default macOS Python 3.9 failed before
`--help`. Its versioned method bundle, Python runtime, specs, and maintainer
prose formed overlapping workflow authorities.

KnoArbor also lacked one explicit lane classifier, machine-checked formal-host
projection, repository Skills for direct and patterned work, and documentation
lifecycle checks equivalent to the reference project's final governance.

## Goals

1. Reuse the pinned product-neutral Harness Core instead of maintaining a
   second lifecycle runtime.
2. Keep KnoArbor-specific paths, owners, Skills, capability/host projections,
   Gates, and branch rules in a typed Adapter.
3. Make Architecture Discovery, Direct Maintenance, Direct SDD, and Patterned
   Harness mutually exclusive.
4. Prevent Harness self-certification; Core/Controller/Adapter/Gate/bootstrap
   changes use Bootstrap Maintenance.
5. Make project context reconstructible from current repository assets rather
   than conversation history.
6. Enforce one current documentation owner and deterministic cleanup rules.
7. Preserve exact capability and semantic responsibility identities through
   admission, design, implementation, review, and acceptance.
8. Keep generated Initiative state, prompts, raw output, credentials, source
   bodies, and private paths out of tracked/portable evidence.
9. Provide a reproducible bootstrap that verifies Core version, commit,
   cleanliness, dependency resolution, Core checks, Adapter checks, and CLI
   startup.
10. Retire the prior Python controller and versioned in-repository method bundle
    without a compatibility fallback.

## Non-Goals

- A general workflow engine or persistent Agent team.
- Forcing ordinary bugs, risky work, or cross-package atomic changes through
  Patterned Harness.
- Copying TAPD, enterprise messaging, multi-repository branch automation, or
  reference-specific benchmark infrastructure.
- Publishing the local Core package or creating a new external repository.
- Moving public documentation solely to imitate another directory layout.
- Storing process narration as current architecture.

## Required Assets

1. **Standards:** lane classification, SDD, documentation governance, and code
   navigation.
2. **Skills:** direct workflow, Patterned Harness Controller, documentation
   curation, and semantic contract review.
3. **Core pin:** exact package/version/commit/path with clean-worktree
   verification.
4. **Adapter:** paths, owners, Skills, Gates, capability maturity, semantic
   hosts, verification mapping, and branch policy.
5. **Rules:** concise project invariants and an authority-safe semantic-host
   projection.
6. **Bootstrap:** frozen install and validation path.
7. **Evidence:** Core tests, Adapter tests, governance/link checks, Skill
   validation, and temporary journey.

## Invariants

1. Patterned Harness admission needs bounded human decisions, at least two
   repository owners, exact delivery units, and one shared acceptance boundary.
2. Unknown owner/authority/lifecycle/recovery/migration/product path routes to
   Architecture Discovery.
3. Frozen one-owner or atomic semantic work uses Direct SDD even when risky or
   cross-package.
4. Harness self-maintenance never runs inside the runtime being replaced.
5. The vendored Core artifact has an exact source commit and SHA-256; when the
   source worktree is present it must match that commit and be clean.
6. The Adapter declares the complete Core-required capability set.
7. Commands are fixed argv arrays; Initiative input cannot inject commands.
8. `CAPABILITY_MAP.md` is the capability maturity authority.
9. `semantic-hosts.json` is only a projection of `CONTRACTS.md`; every host,
   module, owner, and responsibility is checked.
10. Review is ordered `belongs -> authority -> contract -> behavior`; reviewer
    contexts remain read-only and distinct from implementation.
11. Every compatibility seam has one owner, retirement condition, and negative
    oracle.
12. Mutable development state stays in Harness/Git; stable delivered facts
    return to current owners.
13. Retired Python and method-bundle paths do not remain as fallbacks or current
    documentation references.

## Acceptance Criteria

1. A clean setup verifies the exact shared Core artifact and executes
   `pnpm harness -- help`; a present source worktree also passes producer checks.
2. Core typecheck/tests/build/package checks pass at the pin.
3. KnoArbor Adapter typecheck/tests pass.
4. Adapter resolves at least one capability, semantic host, project Skill, and
   owner set from current repository evidence.
5. Single-owner Harness admission is rejected with a Direct SDD route.
6. Documentation governance rejects invalid capability maturity, duplicate host
   responsibility, projection drift, malformed Skills, missing standards, and
   retired Harness authorities.
7. All Markdown links and existing architecture governance pass.
8. The prior Python controller, its unit test, and versioned method bundle are
   removed.
9. The reference reuse manifest classifies every borrowed mechanism as adopt,
   adapt, reject, or defer.
10. One temporary Patterned Harness journey reaches a truthful blocking or
    terminal state without reconstructing chat or persisting raw output.
11. The registry remains Accepted until five real post-adoption Initiatives
    justify promotion.
