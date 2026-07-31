# 1.41 Project Development Harness Verification

## Required Checks

```bash
pnpm harness:bootstrap
pnpm harness:typecheck
pnpm harness:test
uv run python scripts/check-doc-governance.py
uv run python scripts/check-doc-links.py
uv run python scripts/check-architecture.py
uv run python -m unittest tests.test_affected_validation
git diff --check
```

The bootstrap runs the pinned Core's typecheck, tests, build, package import,
Adapter checks, and CLI help. All commands use temporary or ignored state and
must not read user vaults, config, credentials, installed applications, Codex
sessions, or remote systems.

## Contract Tests

Evidence must prove:

- a wrong Core artifact hash, package/version, or installed identity fails
  closed; a present source repository also fails on wrong commit or dirty state;
- single-owner Patterned Harness admission routes to Direct SDD;
- Adapter manifests, fixed argv Gates, owner commands, Skills, capability
  maturity, and semantic hosts validate;
- duplicate capability/host/responsibility IDs, missing owners/modules,
  projection drift, malformed Skills, missing standards, and retired authority
  references fail governance;
- the Core retains its complete lifecycle, artifact, Gate, rollback,
  concurrency, crash, secret, delivery, and closure suite.

## Temporary Journey

Use a temporary Git repository or ignored `.knoarbor/harness` root:

1. create an admission with two owners, one capability delta, exact semantic
   responsibilities, bounded decisions, and shared acceptance;
2. initialize through the KnoArbor composition root;
3. inspect the generated immutable packet and current action;
4. prove a missing role or human decision yields an explicit waiting state;
5. validate persisted evidence contains no private path, raw output, prompt,
   credential, or source body;
6. remove temporary/ignored state.

This migration does not use the old runtime to certify itself. The temporary
journey is post-migration integration evidence; independent cognitive review
remains required for real standard/strict Initiative delivery.

The 2026-07-31 migration journey initialized a clean temporary repository with
`CAP-PUBLIC-API` and `CAP-WEB-CONSOLE`, resolved distinct Python/renderer owners
and their exact formal responsibilities, persisted admission/capability/request
artifacts, and returned `dispatch_role: requirement` at Requirement analysis.
The temporary repository and generated Initiative state were removed after the
observation.

## Upstream And Downstream Delivery

The reusable boundary landed on public `main` through KnoArbor PRs
[#4](https://github.com/pxcg/knoarbor/pull/4) and
[#5](https://github.com/pxcg/knoarbor/pull/5). SieArbor then merged those
public commits through enterprise PR
[#3](https://github.com/pxcg/SieArbor/pull/3), retaining its product identity,
enterprise specifications, objectives, specialist Skills, bilingual
governance, and lifecycle checks while deleting the parallel Python Harness.

Both repositories passed their complete CI jobs, including the new Harness
contract job. The downstream integration used a separate clean worktree; the
existing SieArbor worktree and its unrelated renderer changes were not
modified.

## Adoption Review

Keep lifecycle `Accepted` until five real Initiatives are reviewed for duration,
human intervention, first-pass integration, review rejection, rollback, Gate
flakiness, scope overflow, resume success, delivery duplication, and quality
regression.
