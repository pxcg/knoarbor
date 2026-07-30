# 1.41 Project Development Harness Verification

## Lifecycle

Accepted. Phase 0 evidence is retained below; v2 completion requires the new
contract, control-flow, delivery, and evolution evidence in this document.

## Method Contract Tests

Tests must prove:

- identical failing commands with different timestamps, temporary paths,
  ports, run/task IDs, durations, and progress logs produce the same stored
  failure fingerprint;
- changing the failed test identity, diagnostic code, error class, or
  repository-relative location changes the fingerprint and blocks the delta;
- neither raw output nor volatile values are persisted in checkpoints or
  derived artifacts;

1. all six system layers map to the immutable method bundle; every bundle file
   exists, has a pinned digest, and cross-references only defined stages, roles,
   artifacts, gates, path owners, adapters, and side-effect classes;
2. a v2 manifest pins a version-addressable method path and every digest; moving
   the current pointer does not block an older open run, while mutation of its
   pinned version does;
3. v1, unknown, malformed, secret-bearing, absolute-path, duplicate-ID, and
   unknown-reference records fail with deterministic diagnostics;
4. route-required, conditional, human, gate, artifact, and rollback rules are
   internally complete.

## Workflow And Role Tests

Tests must cover:

- all thirteen stages, legal ordering, typed skips, start, resolve, reject,
  rollback, repeated attempts, restart, and premature closure;
- requirement/design/implementer/reviewer input and output contracts;
- wrong-role output, missing output, changed upstream digest, out-of-scope
  implementation, and Reviewer workspace mutation;
- human approval and rejection, invalid rollback, three-rejection circuit
  breaker, recovery authorization, call budget, and retry budget;
- downstream state invalidation without deletion of prior event evidence;
- closed immutability and repeated closure validation.
- single-writer exclusion, revision/event hash agreement, prepared-state
  recovery, quarantine, and injected crashes at every publish boundary;
- checkpoint transitions atomically include artifact, gate, decision, delivery,
  usage, and blocker state; every auxiliary view can be deleted and regenerated;
- a later Initiative legitimately changing the same paths without invalidating
  a sealed historical run.

## Baseline And Gate Tests

Temporary Git repositories cover:

- tracked, untracked, modified, deleted, missing, symlink, exact-file,
  directory-prefix, and already-dirty scope cases;
- fixed catalog selection and rejection of arbitrary commands or unknown gates;
- argument-array execution without a shell;
- baseline/acceptance passing, identical failure, changed failure, unbaselined
  gate, missing acceptance gate, severity drift, timeout, and process failure;
- hard blocking, complete/incomplete soft scars, scar propagation, and raw gate
  output absence from every persisted record and normal terminal stream;
- canary credentials, environment values, private paths, and source-like output
  redacted from stdout, stderr, exception text, events, gates, handoff, metrics,
  and delivery records;
- separate stable local-observation and release live-model gate identities.

## Knowledge, Handoff, Metrics, And Delivery Tests

Tests must prove:

- project context resolves current registry owners, path-map entries, tests,
  Skills, scope, accepted artifacts, and related local runs without source body;
- portfolio is derived and never becomes feature task authority;
- portable handoff contains no absolute root, secret, prompt, source content, or
  raw command output; Git-backed export/import verifies bundle root hash,
  reachable OID, method availability, artifact digests, and ID conflicts;
- imported bundles retain normalized Requirement/Design/Code Reviewer
  `control_record` verdicts while repository artifacts remain Git references;
- stage duration, attempts, rollback, retries, Agent calls, human decisions,
  gates, scars, scope, delivery, and cycle metrics derive deterministically;
- local delivery is side-effect free;
- GitHub delivery rejects missing authorization, supports dry-run, queries by
  base/head/OID/marker before creation, blocks dirty/uncommitted/unpushed/moved
  heads, reuses only an OID-identical pull request, prevents branch-reuse
  duplicates, and recovers remote-success/local-crash through intent lookup;
- closure delivery substate permits writes only after acceptance, preserves
  acceptance across delivery failure, and requires delivered state for closure;

## End-To-End Temporary Journeys

1. **Fast:** initialize, typed skips, baseline fixed gates, implementation
   artifacts, integration, acceptance gates, local delivery, closure, repeat
   closure.
2. **Strict:** requirement artifacts, human confirmation, reproduction/design
   artifacts, human design confirmation, independent design verdict, baseline,
   implementation/test artifacts, integration gates, independent code verdict,
   human acceptance, local delivery, closure.
3. **Restart:** stop after design confirmation, reload from disk, regenerate the
   Reviewer packet, and continue without in-memory state.
4. **Rollback:** reject design to requirements and code review to implementation;
   verify prior events remain and downstream state resets.
5. **Faults:** exercise changed upstream artifact, scope overflow, hard gate
   delta, incomplete scar, circuit breaker, corrupt JSON, method drift, and
   duplicate external-delivery retry.
6. **Upgrade and concurrency:** advance the current method pointer while an old
   run is open, race two Controllers, and inject exit after each transaction and
   delivery intent/outcome boundary.
7. **Historical seal:** close one run, modify the same paths in a later run, and
   confirm the old seal still verifies internally.

Tests use only temporary repositories, Initiative roots, fake `gh` runners, and
short local subprocesses. They must not read or modify user vaults, config,
`.env`, Codex sessions, credentials, installed applications, or remote systems.

## Required Commands

```bash
uv run --extra dev ruff check scripts/project-development-harness.py \
  scripts/development_harness tests/test_project_development_harness.py
uv run python -m unittest tests.test_project_development_harness \
  tests.test_affected_validation
uv run python scripts/check-doc-governance.py
uv run python scripts/check-doc-links.py
uv run python scripts/plan-affected-validation.py --paths \
  scripts/project-development-harness.py scripts/development_harness \
  tests/test_project_development_harness.py \
  .codex/development \
  docs/DEVELOPMENT.md docs/MAINTAINERS.md docs/TESTING.md \
  specs/README.md specs/registry.json \
  specs/1.41-project-development-harness --run
git diff --check
```

## Phase 0 Evidence

Recorded on 2026-07-22:

- 26 focused kernel, documentation-governance, and affected-planner tests
  passed;
- Ruff, architecture governance, documentation governance, and all 209 local
  Markdown-link checks passed;
- temporary repositories proved workspace baselines, scope attribution,
  manifest immutability, role IDs, budgets, gate delta, scars, secret rejection,
  and idempotent kernel closure;
- no real Initiative used v1 after adoption, so it was not promoted beyond an
  execution kernel.

## Maturity Review

The specification remains `Accepted` after v2 implementation. After five real
Initiatives, review end-to-end duration, human interventions, integration
first-pass rate, design/code rejection rate, rollback targets, gate flakiness,
scope overflow, resume success, delivery duplication, scars, and quality
regressions. Only then decide whether to promote to `Implemented`, revise the
method, or remove stages that lack an independent failure boundary.
