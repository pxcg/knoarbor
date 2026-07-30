# 1.41 Project Development Harness Tasks

## Lifecycle

Accepted; the v1 execution kernel is verified and the v2 complete control-plane
revision is authorized for implementation.

## Stable Failure Identity Root Correction

- [ ] Replace raw subprocess-byte gate fingerprints with a bounded sanitized
  diagnostic projection that removes volatile execution values.
- [ ] Preserve changed failure identities for test names, diagnostic codes,
  assertion/error classes, and repository-relative locations.
- [ ] Add deterministic baseline/integration delta tests proving equal failures
  remain pre-existing while genuinely changed failures block.

## Phase 0: Execution Kernel

- [x] Add versioned Initiative admission, thirteen stages, route requirements,
  role IDs, budgets, workspace baselines, scope delta, gate fingerprints, soft
  scars, secret rejection, and idempotent closure.
- [x] Integrate the kernel with SDD delivery, maintainer docs, affected
  validation, lifecycle governance, and focused tests.
- [x] Record that v1 has no real post-adoption Initiative evidence and remains
  an execution kernel rather than a complete development system.

## Phase 1: Method Contracts

- [x] Add and validate immutable, version-addressable policy, Controller,
  workflow, role, artifact, gate, project-map, and delivery assets under
  `.codex/development/methods/v2/`; map them to the six system layers.
- [x] Pin the method version path and asset digests in every new v2 manifest;
  keep older referenced versions resumable after the current pointer advances.
- [x] Replace arbitrary command gates and incomplete v1 records with the v2
  contract; keep no silent compatibility path.
- [x] Update stable maintainer and SDD-delivery documentation to the v2 owner.

## Phase 2: Relay And Artifact Integrity

- [x] Add append-only events, repository/control artifact storage classes,
  references/digests, typed stage entry/completion, route skips, and role packets.
- [x] Add single-writer locking, monotonic revisions, hash-chained events, atomic
  complete-checkpoint publication, derived views, startup reconciliation, and
  quarantine semantics.
- [x] Enforce role output kinds, artifact attempts/dependencies/lifecycle, write
  boundaries, Controller-persisted Reviewer verdicts, and upstream immutability.
- [x] Add explicit human approve/reject operations, rollback graph, attempt
  history, and three-rejection circuit breaker.
- [x] Prove restart/resume from records without conversation history.

## Phase 3: Deterministic Feedback

- [x] Execute fixed gate profiles without a shell through the redacting summary
  proxy; leak neither raw output nor canary credentials to records or sessions.
- [x] Add A/B gate delta, conditional gate selection, soft-scar propagation,
  and stage eligibility.
- [x] Preserve exact content scope attribution for tracked, untracked, missing,
  dirty, directory-prefix, and symlink cases.
- [x] Bind integration and acceptance completion to required gate and artifact
  evidence.

## Phase 4: Knowledge, Handoff, And Metrics

- [x] Generate fresh Initiative context from registry, project map, Git state,
  scope, owners, tests, and accepted artifacts.
- [x] Add local portfolio and redacted portable handoff without duplicating
  feature task state.
- [x] Add Git-backed portable export/import with root-hash, artifact, method,
  reachable-OID, and local-ID conflict validation.
- [x] Derive stage, rejection, retry, Agent, human, gate, scar, scope, delivery,
  and cycle metrics.
- [x] Reject private paths, secrets, source content, prompts, and raw outputs in
  portable evidence.

## Phase 5: Delivery

- [x] Add a side-effect-free local delivery bundle.
- [x] Add an explicitly authorized GitHub pull-request adapter with dry-run,
  delivery preconditions, intent/outcome recovery, OID-bound idempotency,
  duplicate prevention, and audit records.
- [x] Model delivery as a closure substate and keep delivery retry/failure from
  rewriting accepted product evidence.
- [x] Keep commit, push, issue mutation, notification, and release operations
  outside v2 until separately authorized and specified.

## Phase 6: Verification And Adoption

- [x] Add schema, transition, rollback, role, artifact, gate, scope, handoff,
  metrics, delivery, method-upgrade, concurrency, crash, malformed-input, and
  terminal/record secret-leak regression tests.
- [x] Run one fast and one strict temporary-repository journey plus restart,
  rejection, circuit-breaker, scope-overflow, gate-delta, and delivery-retry
  fault cases.
- [x] Run the affected R3 governance closure and review the final diff for
  duplicate authority, compatibility paths, and active-work overlap.
- [ ] Keep the registry `Accepted` and complete five real post-adoption
  Initiatives before deciding whether v2 is mature enough for `Implemented`.
