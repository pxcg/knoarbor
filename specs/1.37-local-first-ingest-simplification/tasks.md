# 1.37 Local-First Ingest Simplification Tasks

## Status

Accepted target contract. All implementation and verification tasks below
are reset against the KnoArbor 2.3.1 public baseline.

No task may be marked complete by retaining the superseded implementation behind
a compatibility branch. Deletion tasks are first-class acceptance work.

## Phase 0: Freeze And Measure

- [ ] Record the current ingest/runtime/derived/index lifecycle module and line
  counts.
- [ ] Record every API, CLI, desktop, and maintenance call into ingest execution
  or machine-index publication.
- [ ] Add architecture tests that fail while runtime registries, derived jobs,
  segment results, or public CURRENT switching remain.
- [ ] Freeze implementation changes to specifications 1.28 through 1.36 except
  migration notes pointing here.

## Phase 1: Store v5

- [ ] Define `transactional_ingest.v5` schema.
- [ ] Add singleton `materialization_state` and typed store methods.
- [ ] Add atomic `request_materialization` to factual and wiki mutation
  transactions.
- [ ] Add bulk attempt/task projection with SQL ordering and limit.
- [ ] Add explicit force invocation identity.
- [ ] Add owner-driven transition from running to `recovery_needed` on shutdown.
- [ ] Remove `waiting_admission` as a durable task state.
- [ ] Remove `derived_jobs`, `DerivedJobLease`, and `segment_results` from the
  normal schema.

## Phase 2: Operation-Owned Executor

- [ ] Extract `IngestTaskExecutor.execute(task_id, cancellation_token)` from the
  dispatcher.
- [ ] Make provider admission interruptible by user cancel and app shutdown.
- [ ] Replace lease-renewal thread with explicit renewal around model and commit
  boundaries.
- [ ] Make desktop submission schedule exactly one operation-owned execution.
- [ ] Make CLI submission execute the same method in the foreground.
- [ ] Add one startup reconciliation scan without persistent polling.
- [ ] Delete runtime and dispatcher registries, wake generations, and persistent
  mode flags.

## Phase 3: Source-Level Recovery

- [ ] Make committed source revision identity the sole model-work skip boundary.
- [ ] Ensure an uncommitted source is safely rerun after attempt recovery.
- [ ] Remove segment-result reads, writes, retention, and tests.
- [ ] Remove prepared-result/checkpoint remnants from runtime production imports.
- [ ] Verify repeated force invocations create distinct task and revision ids.

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
- [ ] Report configured capacity separately from event-derived peak concurrency,
  and distinguish attempts/retries from semantic usage records.
- [ ] Retain per-segment semantic usage and persist the attempt ID on each
  published source processing record.

## Phase 4: Vault Materializer

- [ ] Introduce `VaultMaterializer` and materialization token model.
- [ ] Route factual commits and all KnoArbor wiki mutations through requested
  epoch increments.
- [ ] Acquire one vault write lock around application-controlled page mutation
  and materialization.
- [ ] Add stable wiki tree fingerprint before and after index scanning.
- [ ] Add `building -> prepared -> clean` publication journal.
- [ ] Resume prepared CURRENT publication idempotently.
- [ ] Return dirty when fingerprint or requested epoch changes; one call never
  spins across epochs.
- [ ] Remove per-source projection jobs, blocked index state, and drain loops.
- [ ] Make raw CURRENT switch private to bootstrap, migration, and materializer
  internals.

## Phase 5: Public Surface Cleanup

- [ ] Route API, CLI, and desktop cancellation through one application service.
- [ ] Replace derived-view repair with materialization rebuild.
- [ ] Update queued execution copy to describe local-process lifetime.
- [ ] Update run list/read to use bounded bulk SQLite projection.
- [ ] Remove old repair command, route, response schema, and documentation rather
  than adding an alias.
- [ ] Update backup/recovery documentation for v5 state.

## Phase 6: Migration

- [ ] Implement read-only v4 preflight under migration lock.
- [ ] Migrate derived state into one dirty materialization epoch.
- [ ] Convert expired running attempts to `recovery_needed`.
- [ ] Drop superseded tables in the v5 database transaction.
- [ ] Remove obsolete runtime directories after the database commit.
- [ ] Verify or rebuild CURRENT, then complete the migration journal.
- [ ] Add restart tests at every migration phase.
- [ ] Confirm no v4 runtime branch remains.

## Phase 7: Verification And Deletion Gate

- [ ] Pass every crash-boundary scenario in `verification.md`.
- [ ] Pass desktop, local API, and CLI parity tests.
- [ ] Pass two-local-process claim and vault-lock tests.
- [ ] Pass external wiki mutation during index build test.
- [ ] Pass bounded shutdown tests with no live worker after return.
- [ ] Run full Python and frontend verification suites.
- [ ] Compare final complexity metrics with Phase 0 and reject the change if
  lifecycle code or owner count did not materially decrease.
- [ ] Update specifications 1.32 and 1.36 to show they are superseded by 1.37.

## Implementation Order Constraint

The implementation must proceed store -> executor -> materializer -> adapters ->
deletions -> migration. Adapter-first patches are prohibited because they would
create another temporary authority path.

## Closure Review

- [ ] Introduce `IngestExecutionSession` as the only mutable lease and factual
  publication owner visible to execution.
- [ ] Remove public `update_index` and `update_machine_index` entry points.
- [ ] Route initialization and all application-controlled wiki mutations through
  `VaultMaterializer`.
- [ ] Make page identity resolution read authoritative local Markdown instead
  of relying on index refresh side effects.
- [ ] Make one materializer call consume at most one epoch and discard unstable
  index generations.
- [ ] Remove eager pipeline package re-exports that caused cross-layer import
  initialization.
- [ ] Move deterministic Markdown projection into storage so materialization has
  no dependency on the pipeline package.
- [ ] Prune index generations unreachable from CURRENT or materialization state
  during startup before readers and queued work are admitted.
- [ ] Add architecture assertions for the closed ownership boundaries.

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

- [ ] Accept the versioned source, knowledge, diagnostics, and manifest payloads
  from 1.26.
- [ ] Stage under `.knoarbor/facts/.staging` and atomically publish to the
  deterministic 1.17 revision path.
- [ ] Make verified crash-left targets resumable and conflicting targets fail
  integrity checks.
- [ ] Make active readers resolve only the SQLite-selected fact manifest.
- [ ] Add restartable legacy-generation conversion to the bounded startup scan.
- [ ] Reclaim unreachable staging and fact directories during startup.
- [ ] Delete old fact path and filename readers/writers after migration closes.

## Phase 10: Resolved Vault Command Amendment

- [ ] Replace the v1 command with a v2 command that persists resolved vault
  path, vault identity, and optional configured profile ID.
- [ ] Reload explicit-path commands by path and profile commands by ID, then
  verify the recorded path and identity before execution or recovery.
- [ ] Delete the v1 command shape instead of retaining a compatibility branch.
- [ ] Verify explicit-path CLI admission against a config whose default vault
  differs, configured-profile admission, and path/identity mismatch rejection.

## Phase 11: MinerU Identity Root Fix

- [ ] Preserve source-relative parents for folder preprocessing outputs.
- [ ] Align MinerU readiness diagnostics with endpoint configuration rather
  than the retired persistent input directory.
- [ ] Verify nested same-stem inputs and single-file output compatibility.

## Phase 12: MinerU Transport And Contract Closure

- [ ] Restore the production HTTP transport as a processor method and exercise
  it through the real processor in tests.
- [ ] Serialize native multipart booleans, language lists, and upload media
  types according to the MinerU `/file_parse` contract.
- [ ] Preserve canonical backend and advanced form values across config saves.
- [ ] Align canonical backend values with the MinerU 3.1 `/file_parse`
  contract and remove unsupported backend choices.
- [ ] Materialize safe ZIP responses and reject unsafe archive members.
- [ ] Probe the MinerU `/health` endpoint for readiness diagnostics.
- [ ] Verify JSON, ZIP, attachment, config round-trip, and health behavior.

## Phase 13: Ingest Validation Clean Path

- [ ] Validate canonical generation IDs and contain every manifest member
  beneath its immutable generation directory.
- [ ] Require every document payload to belong to the verified file inventory.
- [ ] Unify dry-run and write source outcome calculation.
- [ ] Delete `rejected` source/segment handling and duplicate semantic gate
  compatibility fields.

## Phase 14: Active-Revision Image Cleanup

- [ ] Derive cleanup candidates only from persisted image attachment paths
  contained by `raw/derived/assets/images`.
- [ ] Release unreferenced candidates after successful full-source head
  replacement and Raw source purge.
- [ ] Protect images referenced by any active source or session revision.
- [ ] Verify reingest, deletion, shared-image retention, containment, failed
  publication, and idempotent publication behavior.
