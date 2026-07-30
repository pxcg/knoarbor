# 1.37 Local-First Ingest Simplification Tasks

## Status

Accepted. The local-first baseline verification passed on 2026-07-10; Phase 8
knowledge revision work remains in progress.

No task may be marked complete by retaining the superseded implementation behind
a compatibility branch. Deletion tasks are first-class acceptance work.

## Phase 0: Freeze And Measure

- [x] Record the current ingest/runtime/derived/index lifecycle module and line
  counts.
- [x] Record every API, CLI, desktop, and maintenance call into ingest execution
  or machine-index publication.
- [x] Add architecture tests that fail while runtime registries, derived jobs,
  segment results, or public CURRENT switching remain.
- [x] Freeze implementation changes to specifications 1.28 through 1.36 except
  migration notes pointing here.

## Phase 1: Store v5

- [x] Define `transactional_ingest.v5` schema.
- [x] Add singleton `materialization_state` and typed store methods.
- [x] Add atomic `request_materialization` to factual and wiki mutation
  transactions.
- [x] Add bulk attempt/task projection with SQL ordering and limit.
- [x] Add explicit force invocation identity.
- [x] Add owner-driven transition from running to `recovery_needed` on shutdown.
- [x] Remove `waiting_admission` as a durable task state.
- [x] Remove `derived_jobs`, `DerivedJobLease`, and `segment_results` from the
  normal schema.

## Phase 2: Operation-Owned Executor

- [x] Extract `IngestTaskExecutor.execute(task_id, cancellation_token)` from the
  dispatcher.
- [x] Make provider admission interruptible by user cancel and app shutdown.
- [x] Replace lease-renewal thread with explicit renewal around model and commit
  boundaries.
- [x] Make desktop submission schedule exactly one operation-owned execution.
- [x] Make CLI submission execute the same method in the foreground.
- [x] Add one startup reconciliation scan without persistent polling.
- [x] Delete runtime and dispatcher registries, wake generations, and persistent
  mode flags.

## Phase 3: Source-Level Recovery

- [x] Make committed source revision identity the sole model-work skip boundary.
- [x] Ensure an uncommitted source is safely rerun after attempt recovery.
- [x] Remove segment-result reads, writes, retention, and tests.
- [x] Remove prepared-result/checkpoint remnants from runtime production imports.
- [x] Verify repeated force invocations create distinct task and revision ids.

## Capability-Derived Concurrency Amendment

- [ ] Remove numeric ingest concurrency from the public configuration surface.
- [ ] Freeze the code-derived semantic concurrency policy in each immutable
  execution contract.
- [ ] Execute segment calls in deterministic adaptive waves while preserving
  source-order merge and serial factual publication.
- [ ] Read MinerU `max_concurrent_requests` and parallelize only independent
  rich-file conversion.
- [ ] Admit each frozen converted document to the semantic ready queue without
  waiting for every rich file in the folder to finish conversion.
- [ ] Run multiple ready sources concurrently under the one aggregate provider
  admission policy and retain deterministic result order.
- [ ] Verify committed sources skip and uncommitted sources restart as a whole.
- [x] Report configured capacity separately from event-derived peak concurrency,
  and distinguish attempts/retries from semantic usage records.
- [x] Retain per-segment semantic usage and persist the attempt ID on each
  published source processing record.

## Phase 4: Vault Materializer

- [x] Introduce `VaultMaterializer` and materialization token model.
- [x] Route factual commits and all KnoArbor wiki mutations through requested
  epoch increments.
- [x] Acquire one vault write lock around application-controlled page mutation
  and materialization.
- [x] Add stable wiki tree fingerprint before and after index scanning.
- [x] Add `building -> prepared -> clean` publication journal.
- [x] Resume prepared CURRENT publication idempotently.
- [x] Return dirty when fingerprint or requested epoch changes; one call never
  spins across epochs.
- [x] Remove per-source projection jobs, blocked index state, and drain loops.
- [x] Make raw CURRENT switch private to bootstrap, migration, and materializer
  internals.

## Phase 5: Public Surface Cleanup

- [x] Route API, CLI, and desktop cancellation through one application service.
- [x] Replace derived-view repair with materialization rebuild.
- [x] Update queued execution copy to describe local-process lifetime.
- [x] Update run list/read to use bounded bulk SQLite projection.
- [x] Remove old repair command, route, response schema, and documentation rather
  than adding an alias.
- [x] Update backup/recovery documentation for v5 state.

## Phase 6: Migration

- [x] Implement read-only v4 preflight under migration lock.
- [x] Migrate derived state into one dirty materialization epoch.
- [x] Convert expired running attempts to `recovery_needed`.
- [x] Drop superseded tables in the v5 database transaction.
- [x] Remove obsolete runtime directories after the database commit.
- [x] Verify or rebuild CURRENT, then complete the migration journal.
- [x] Add restart tests at every migration phase.
- [x] Confirm no v4 runtime branch remains.

## Phase 7: Verification And Deletion Gate

- [x] Pass every crash-boundary scenario in `verification.md`.
- [x] Pass desktop, local API, and CLI parity tests.
- [x] Pass two-local-process claim and vault-lock tests.
- [x] Pass external wiki mutation during index build test.
- [x] Pass bounded shutdown tests with no live worker after return.
- [x] Run full Python and frontend verification suites.
- [x] Compare final complexity metrics with Phase 0 and reject the change if
  lifecycle code or owner count did not materially decrease.
- [x] Update specifications 1.32 and 1.36 to show they are superseded by 1.37.

## Implementation Order Constraint

The implementation must proceed store -> executor -> materializer -> adapters ->
deletions -> migration. Adapter-first patches are prohibited because they would
create another temporary authority path.

## Closure Review

- [x] Introduce `IngestExecutionSession` as the only mutable lease and factual
  publication owner visible to execution.
- [x] Remove public `update_index` and `update_machine_index` entry points.
- [x] Route initialization and all application-controlled wiki mutations through
  `VaultMaterializer`.
- [x] Make page identity resolution read authoritative local Markdown instead
  of relying on index refresh side effects.
- [x] Make one materializer call consume at most one epoch and discard unstable
  index generations.
- [x] Remove eager pipeline package re-exports that caused cross-layer import
  initialization.
- [x] Move deterministic Markdown projection into storage so materialization has
  no dependency on the pipeline package.
- [x] Prune index generations unreachable from CURRENT or materialization state
  during startup before readers and queued work are admitted.
- [x] Add architecture assertions for the closed ownership boundaries.

## Phase 8: Knowledge Revision Contract

- [ ] Accept only linked revision drafts from specifications 1.26 and 1.27.
- [ ] Persist source contributions separately from canonical entity snapshots.
- [ ] Persist claims with canonical entity IDs and relations with canonical
  endpoint/supporting-claim IDs.
- [ ] Persist bounded revision diagnostics outside factual retrieval.
- [ ] Remove wall-clock projection non-determinism.
- [ ] Carry one fact generation through Wiki and machine-index outputs.
- [ ] Expose composite facts/materialization status consistently.
- [ ] Separate `retry_processing` from model-free `rebuild_projection`.

## Phase 9: Fact Layout Amendment

- [x] Accept the versioned source, knowledge, diagnostics, and manifest payloads
  from 1.26.
- [x] Stage under `.knoarbor/facts/.staging` and atomically publish to the
  deterministic 1.17 revision path.
- [x] Make verified crash-left targets resumable and conflicting targets fail
  integrity checks.
- [x] Make active readers resolve only the SQLite-selected fact manifest.
- [x] Add restartable legacy-generation conversion to the bounded startup scan.
- [x] Reclaim unreachable staging and fact directories during startup.
- [x] Delete old fact path and filename readers/writers after migration closes.

## Phase 10: Resolved Vault Command Amendment

- [x] Replace the v1 command with a v2 command that persists resolved vault
  path, vault identity, and optional configured profile ID.
- [x] Reload explicit-path commands by path and profile commands by ID, then
  verify the recorded path and identity before execution or recovery.
- [x] Delete the v1 command shape instead of retaining a compatibility branch.
- [x] Verify explicit-path CLI admission against a config whose default vault
  differs, configured-profile admission, and path/identity mismatch rejection.

## Phase 11: MinerU Identity Root Fix

- [x] Preserve source-relative parents for folder preprocessing outputs.
- [x] Align MinerU readiness diagnostics with endpoint configuration rather
  than the retired persistent input directory.
- [x] Verify nested same-stem inputs and single-file output compatibility.

## Phase 12: MinerU Transport And Contract Closure

- [x] Restore the production HTTP transport as a processor method and exercise
  it through the real processor in tests.
- [x] Serialize native multipart booleans, language lists, and upload media
  types according to the MinerU `/file_parse` contract.
- [x] Preserve canonical backend and advanced form values across config saves.
- [x] Align canonical backend values with the MinerU 3.1 `/file_parse`
  contract and remove unsupported backend choices.
- [x] Materialize safe ZIP responses and reject unsafe archive members.
- [x] Probe the MinerU `/health` endpoint for readiness diagnostics.
- [x] Verify JSON, ZIP, attachment, config round-trip, and health behavior.

## Phase 13: Ingest Validation Clean Path

- [ ] Validate canonical generation IDs and contain every manifest member
  beneath its immutable generation directory.
- [ ] Require every document payload to belong to the verified file inventory.
- [ ] Unify dry-run and write source outcome calculation.
- [ ] Delete `rejected` source/segment handling and duplicate semantic gate
  compatibility fields.

## Phase 14: Active-Revision Image Cleanup

- [x] Derive cleanup candidates only from persisted image attachment paths
  contained by `raw/derived/assets/images`.
- [x] Release unreferenced candidates after successful full-source head
  replacement and Raw source purge.
- [x] Protect images referenced by any active source or session revision.
- [x] Verify reingest, deletion, shared-image retention, containment, failed
  publication, and idempotent publication behavior.
