# 1.37 Local-First Ingest Simplification Verification

## Verification Policy

The design is accepted only when correctness and deletion are both verified.
A green regression suite does not compensate for a retained duplicate authority,
polling loop, compatibility fallback, or unbounded lifecycle thread.

## Invariant Matrix

| Invariant | Required evidence |
| --- | --- |
| One workflow authority | Static call graph and tests show ingest decisions read SQLite only |
| No online-service runtime | No registry/dispatcher modules and no empty polling thread |
| Immediate local execution | Desktop schedules once; CLI runs foreground executor |
| Crash recovery | Startup scan repairs expired attempts and dirty materialization |
| One local writer | Two-process vault lock tests serialize mutation/publication |
| Immutable admitted input | Source mutation after submit cannot change execution |
| Source-level idempotency | Recovery skips committed source and reruns uncommitted source |
| No segment recovery authority | No segment/prepared table, file, import, or runtime branch |
| No lost materialization | Requested epoch greater than published epoch always triggers successor |
| Stable external-file snapshot | Fingerprint change during scan prevents CURRENT publication |
| Atomic machine index | Reader sees one verified immutable generation |
| Bounded shutdown | No owned worker is alive after shutdown returns |
| Force invocation | Repeated force requests create different tasks and factual revisions |
| Bounded run listing | One SQL projection applies ordering and limit before file enrichment |

## Required Automated Tests

### Task And Attempt

- exact normal command submission is idempotent;
- every force submission creates a new task;
- two local processes claiming one attempt produce one owner;
- claim cannot occur while paused or before provider admission;
- stale and expired leases cannot publish facts or finish;
- cancellation and shutdown interrupt admission waits;
- shutdown of a running task leaves a terminal or `recovery_needed` attempt;
- no thread remains alive after executor shutdown.

### Input And Source Recovery

- changing the original source after submission does not change execution;
- corrupt input generation is rejected before claim;
- crash before source commit repeats model work on recovery;
- crash after source commit skips model work for that source;
- multi-source recovery skips committed sources and processes remaining sources;
- no test fixture or production code creates segment/prepared recovery state.

### Materialization

- one factual commit increments requested epoch in the same transaction;
- multiple factual commits coalesce into one final local materialization;
- application wiki edit increments requested epoch under vault lock;
- refresh requested during build produces a successor epoch;
- external file mutation during scan invalidates the prepared generation;
- crash during Markdown projection leaves state dirty and is rewritten;
- crash during index staging leaves CURRENT unchanged;
- crash after prepared phase publishes the recorded generation on startup;
- crash after CURRENT replacement marks the same generation clean;
- source projection or index failure leaves facts readable and materialization
  explicitly failed/dirty;
- explicit rebuild invokes no model call.

### Index Readers

- CURRENT path traversal is rejected;
- generation manifest and every artifact hash are verified;
- generation identity binds fact generation and wiki fingerprint;
- old snapshot remains readable while a new generation publishes;
- machine page body and graph always come from one snapshot;
- no transactional caller can invoke the raw CURRENT switch.

### Startup Reconciliation

- startup scan exits after finite work and leaves no polling thread;
- queued startup policy schedules each eligible task once;
- expired running attempt becomes `recovery_needed`;
- dirty materialization rebuilds without model calls;
- prepared publication resumes idempotently;
- clean vault startup performs no write;
- dynamically admitted vault executes immediately without registration.

### API, CLI, And Desktop

- all surfaces call `IngestApplicationService`;
- all surfaces read the same SQLite attempt projection;
- all surfaces cancel through the same SQLite method;
- CLI process exits with no background worker;
- local API shutdown joins all operation-owned work;
- removed derived-view repair names return an explicit unsupported contract in
  migration tests and are absent from current route/parser snapshots.
- an explicit CLI `--vault` path survives configuration reload even when the
  configured default points elsewhere;
- a configured vault profile still reloads by profile ID;
- execution rejects any recorded path, identity, or profile mismatch before a
  task lease is claimed.

### Migration

- v4 preflight failure leaves schema and CURRENT unchanged;
- v4 active facts become one v5 requested fact generation;
- queued attempts remain queued;
- expired running attempts become `recovery_needed`;
- derived failed/blocked/queued state becomes one dirty materialization state;
- segment result rows and old runtime directories are removed;
- CURRENT is retained only when verified against current token;
- restart after DB commit completes materialization and migration;
- a second migration run is a no-op;
- production source contains no v4 fallback branch.

## Fault Injection Matrix

Each boundary must be tested by raising or terminating immediately after it:

1. input generation staging;
2. task transaction commit;
3. provider admission acquisition;
4. attempt claim;
5. model response receipt;
6. immutable fact-file rename;
7. factual SQLite commit;
8. generated Markdown atomic replace;
9. index artifact staging;
10. materialization prepared transaction;
11. CURRENT atomic replace;
12. materialization clean transaction;
13. attempt finish transaction;
14. migration DB commit;
15. migration CURRENT publication.

For every fault, the expected next-start action must be asserted. Tests may not
accept silent fallback to a legacy file or state.

## Static Deletion Gates

The following searches must return no production matches, excluding migration
diagnostics and this specification:

```text
IngestRuntimeRegistry
IngestDispatcherRegistry
DerivedViewDispatcherRegistry
DerivedJobLease
claim_derived_job
segment_results
ingest/segments
ingest/prepared
repair-derived-views
```

Additional architecture checks must prove:

- no `while` loop performs an empty vault queue poll;
- no CLI/API adapter imports raw run-file cancellation;
- no public function switches transactional index CURRENT;
- no production module reads `core.checkpoints` for ingest planning;
- no task lifecycle decision reads JSON.

## Complexity Gate

Before implementation, record baseline counts for:

- ingest lifecycle production lines;
- worker/registry classes;
- thread types;
- lease types;
- durable task/materialization states;
- SQLite ingest tables;
- workflow authority files.

Release requires:

- zero persistent vault worker classes;
- zero derived lease types;
- zero segment recovery stores;
- one fewer or equal SQLite table count after v5 migration;
- at least 25 percent fewer ingest lifecycle lines than the 1.36 baseline;
- no increase in public ingest concepts.

If the line-count goal cannot be met, implementation stops for design review
rather than weakening the gate.

## Performance Checks

- run list cost is bounded by requested limit, not total attempt history;
- clean startup cost is one bounded query per configured vault;
- clean machine query performs no write;
- materialization performs one final index build per stable requested epoch;
- no idle database or filesystem polling occurs;
- model concurrency remains within the immutable code-derived process-local
  admission policy;
- semantic concurrency grows only after a fully successful wave and never
  exceeds pending segment count;
- MinerU folder concurrency honors a reported positive
  `max_concurrent_requests` value and falls back to one when absent;
- a serial MinerU producer overlaps with semantic execution of already frozen
  documents, and multiple ready documents can have model work in flight;
- concurrent completion order does not change input generation order, factual
  identity, segment merge order, or committed output.
- report attempt/response/failure/retry and peak in-flight counts match the run
  event stream, while each processed segment reports its own usage;
- unavailable event telemetry is rendered as `n/a`, never a fabricated zero;
- every published source processing record identifies its owning attempt.

## Knowledge Revision Integration

- publication preserves aliases, evidence, claim entity IDs, relation endpoint
  IDs, and supporting-claim IDs;
- restart returns the same typed factual revision;
- factual commit followed by projection failure reports
  `materialization_pending` and preserves facts;
- a missing projection remains a rebuildable pending-view response until
  materialization is clean; only a clean missing target is authoritative 404;
- `rebuild_projection` performs zero semantic calls;
- repeated rebuild produces canonically identical content;
- page, graph, search, source locator, and raw evidence readers use one fact
  generation;
- CLI, API, desktop, reports, and startup agree on composite status.
- one publication creates exactly the 1.17 four-file fact tree;
- identical publication is idempotent and a conflicting target is rejected;
- crash before rename removes staging, while crash after rename leaves an
  unreachable fact tree that startup safely reclaims;
- crash after source-head switch preserves the selected fact revision and
  triggers model-free materialization;
- legacy fact migration makes zero semantic calls and leaves no production
  fallback reader after completion.

## Manual Product Checks

- start ingest in desktop, close during provider wait, relaunch, and resume;
- close after at least one source committed, relaunch, and confirm committed
  source is not model-processed again;
- run the same ingest from CLI and confirm no process remains;
- invoke force twice and confirm two run/task identifiers;
- edit a page while index rebuild is intentionally delayed and confirm the final
  snapshot contains the edit;
- edit a wiki file externally during rebuild and confirm unstable generation is
  not published;
- inspect UI run history after several recoveries and confirm all attempts are
  visible without noticeable list degradation.

## Final Commands

The implementation task must record exact repository commands after dependency
inspection. At minimum:

```text
git diff --check
uv run ruff check src/knoarbor tests
uv run python -m compileall -q src/knoarbor
uv run python -m unittest discover -s tests -p 'test_*.py'
```

Frontend typecheck/build and desktop tests are required when public route,
response, or lifecycle behavior changes.

## Current Result

Implementation baseline recorded before v5 edits:

- lifecycle scope: 3,542 production lines across transactional store, runtime,
  ingest/derived dispatchers, derived views, retention, ingest pipeline,
  coordinator, and run projection;
- three vault worker/registry modules;
- two lease types (`AttemptLease`, `DerivedJobLease`);
- two additional durable recovery/derivation tables (`derived_jobs`,
  `segment_results`);
- API lifespan, coordinator, CLI, and index refresh all call the superseded
  runtime/outbox path.

Implementation verification completed on 2026-07-10:

- lifecycle scope: 2,645 production lines, down 897 lines (25.32 percent)
  from the 3,542-line baseline;
- zero persistent vault worker/registry modules;
- one lease type (`AttemptLease`) and no renewal thread;
- no `derived_jobs`, `DerivedJobLease`, `segment_results`, or `task_commands`;
- one vault-level `materialization_state` with resumable prepared publication;
- v4-only preflight and migration to v5, with older formats rejected;
- two-process claim and vault-lock tests pass;
- external mutation during index scanning is detected and rebuilt before
  `CURRENT` publication;
- final full Python suite: 588 tests passed;
- Ruff, compileall, renderer production build, desktop typecheck, and desktop
  renderer integration checks pass.

## MinerU Identity And Readiness Verification

- A folder fixture containing `a/report.pdf` and `b/report.pdf` produces two
  distinct Markdown files with the matching relative parents.
- A direct-file fixture still produces `<output>/<stem>.md`.
- A production-processor fixture patches only the HTTP client and proves the
  real transport sends the native multipart request.
- An enabled, reachable MinerU endpoint reports `ready`; an unreachable service
  reports `endpoint_unreachable`; a missing endpoint reports
  `endpoint_missing`.
- JSON and ZIP fixtures both materialize Markdown and attachments; traversal
  archive members fail without writing outside the derived output root.
- Canonical backend, parse mode, patterns, recursion, language list, response
  flags, server URL, and page bounds survive a UI config round trip.
- The config boundary accepts only `pipeline`, `vlm-auto-engine`, and
  `hybrid-auto-engine`; legacy short engine names migrate to the matching
  official value and all other backend names fail explicitly.

## Ingest Validation Clean-Path Verification

- Invalid generation IDs, absolute manifest members, parent traversal, and
  document members absent from the hashed inventory fail before execution.
- Dry-run and write produce the same `processed` or `partial` semantic result.
- A compiler-integrity violation is `failed`; no public or persisted
  `rejected` outcome remains.
- Reports and recovery policy consume the unified outcomes without translating
  removed compatibility fields.

## Active-Revision Image Cleanup Verification

Focused source-revision and page-deletion tests must prove:

- replacing a full-source revision removes an image referenced only by the
  superseded source revision;
- reingest preserves a candidate image when another active source references
  the same path;
- replacing the final active reference later removes the shared image;
- deleting a Raw-backed page removes every unshared image recorded by that
  source's revisions while preserving active shared images;
- attachment paths outside `raw/derived/assets/images`, absolute paths,
  traversal paths, and non-image attachments are never deleted;
- a failed source-head publication and an idempotently reused revision do not
  remove images;
- session-window publication does not remove images owned by an earlier active
  window.

Run:

```text
uv run python -m unittest tests.test_source_revisions tests.test_wiki_pages
uv run python scripts/check-doc-governance.py
uv run python scripts/check-doc-links.py
git diff --check
```
