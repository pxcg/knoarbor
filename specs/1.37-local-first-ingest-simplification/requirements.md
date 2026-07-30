# 1.37 Local-First Ingest Simplification Requirements

## Status

Accepted target contract for public convergence. Implementation remains
pending against the KnoArbor 2.3.1 baseline. The authoritative lifecycle and
owner domain are registered in `specs/registry.json`.

This specification is the sole public owner for the target local-first ingest
lifecycle. No public specifications 1.28 through 1.36 are activated. Immutable
input generations, transactional factual revisions, and immutable index
generations remain valid unless explicitly changed here.

## Product Context

KnoArbor is a local, single-user application. The desktop application, its
loopback HTTP process, and the CLI operate on local vault files and local
SQLite databases. The application is not an online service and does not promise
background execution while it is closed.

External network access is limited to explicit capabilities such as model API
calls and software updates. There is no multi-machine worker fleet, distributed
queue, remote database, or server-side vault owner.

The design must tolerate more than one local process, such as the desktop app
and a CLI command touching the same vault, but it must not import distributed
systems machinery for that case.

## Goals

1. Make the normal ingest path understandable as one local operation.
2. Preserve crash-safe task, factual revision, cursor, and index publication.
3. Resume incomplete work when the application next starts or the user retries.
4. Serialize local vault mutations across threads and local processes.
5. Keep model calls outside vault-write critical sections.
6. Make every derived artifact rebuildable from committed facts and local wiki
   content.
7. Remove background polling, wake reliability, duplicate recovery authorities,
   and per-derived-job lease machinery.
8. Keep API, CLI, and desktop behavior on one application service boundary.
9. Define explicit behavior for cancellation, force reprocessing, partial
   failure, and application shutdown.
10. Leave the implementation materially smaller than the architecture it
    replaces.

## Non-Goals

- Continuing ingest while the desktop application is closed.
- Distributed execution, leader election, remote worker coordination, or
  cross-machine exactly-once delivery.
- Exactly-once model API calls. A crash may require repeating an uncommitted
  model call.
- Segment-level model-call resume in the base architecture.
- Treating Markdown projections or machine indexes as factual authority.
- Coordinating arbitrary external editors with database transactions. External
  file changes are detected and reconciled, not transactionally controlled.
- Preserving removed internal tables or runtime modules as compatibility
  fallbacks.

## Required Invariants

### R1. One Workflow Authority

SQLite is the only workflow authority for tasks, attempts, cancellation,
leases, factual revisions, source heads, cursors, and materialization state.
JSON run files and event logs are observations only.

### R2. Operation-Owned Execution

Submitting an ingest schedules that task immediately in the current local
process. The desktop local service uses an operation-owned executor. The CLI
executes the same task protocol in its foreground process. Neither surface
creates a persistent vault worker registry.

### R3. Startup Reconciliation

Application startup performs one bounded scan of configured vaults. It repairs
expired attempts, resumes eligible queued tasks according to user settings, and
reconciles dirty materialization. It does not start an empty polling loop.

### R4. Local Concurrency

SQLite claims prevent duplicate task execution. One cross-process vault write
lock serializes factual publication, generated Markdown writes, manual
application page mutations, and index publication. OS lock release is the
process-crash recovery boundary.

### R5. Immutable Admitted Input

The executor reads only a verified immutable input generation. Original source
paths may be retained as provenance but cannot be reread during execution or
recovery.

### R6. Source-Level Recovery

Committed source revisions are idempotent. Recovery may repeat model work for
an uncommitted source, but it skips source inputs whose factual revision key is
already committed. No mutable segment or prepared-result cache participates in
workflow decisions.

### R7. Factual Commit Before Derivation

Source revision, source head or session watermark, cursor, and entity
contributions commit in one SQLite transaction while the attempt lease is
current. That transaction also advances the vault materialization request
epoch.

### R8. One Materialization State

Each vault has one materialization state, not a queue of source-projection and
index jobs. It records requested epoch, published epoch, requested fact
generation, prepared index generation, phase, and error.

### R9. No Lost Refresh

Every application-controlled factual or wiki mutation increments the requested
materialization epoch. A build publishes only the epoch it captured. If a newer
epoch arrives while it is building, it loops and builds the successor before
declaring the vault clean.

### R10. Atomic Machine Snapshot

Machine index artifacts are built in an immutable generation, verified, and
selected by atomic `CURRENT` replacement. A prepared publication phase is
persisted before `CURRENT` changes so startup can finish or retry publication
idempotently.

### R11. Explicit Shutdown

Application shutdown signals every operation-owned task. Work waiting for
provider admission returns to `queued`; claimed work stops scheduling new model
calls and becomes `recovery_needed` unless it can finish promptly. Shutdown
cannot return while an owned worker continues to claim new work.

### R12. Force Means New Invocation

Every explicit force-reprocess request creates a new task invocation even when
input and execution contract are identical. Recovery remains an attempt under
the same task and does not change factual identity.

### R13. Typed Factual Input

The factual publication port accepts only a linked source knowledge revision
draft defined by specifications 1.26 and 1.27. Runtime code does not reinterpret
model positions, aliases, claim names, or relation semantics.

### R14. Facts And Visibility Are Distinct

Public status distinguishes failure before commit, facts committed with
materialization pending, visible materialization, and partial source success.
Presentation does not hide a pending projection behind an incidental summary
field.

### R15. Projection Recovery Is Model-Free

`rebuild_projection` reads published revisions and never creates an ingest
attempt or invokes a model. `retry_processing` reuses immutable input and may
perform semantic calls.

### R16. Deterministic Projection Generation

Materialization consumes one factual generation and renderer contract.
Wall-clock time does not alter canonical projection content. Wiki, graph,
search, and source locator records published together identify the same fact
generation.

### R17. One Published Fact Tree

Publication stages the four payloads defined by 1.26 under the 1.17 fact
layout, verifies their manifest, atomically renames them to one deterministic
revision directory, and then selects that revision through the SQLite source
head. Readers never infer an active revision from directory names or times.

### R18. Bounded Fact-Layout Migration

Legacy active generations migrate without model calls under the existing
migration journal and vault lock. The migration verifies semantic identity and
hashes before switching source heads. Completion removes the old tree and old
reader; runtime does not retain dual-path fallback behavior.

### R19. Resolved Vault Execution Identity

Every immutable ingest command persists the resolved absolute vault path and
vault identity used at admission. A configured vault selection additionally
persists its profile ID; an explicit automation path does not invent or inherit
an unrelated profile ID. Execution and recovery reload the recorded selection
and reject path, identity, or configured-profile drift before claiming work.

### R20. Capability-Derived Local Concurrency

Document conversion and semantic extraction are separate admission domains.
The application derives their effective concurrency in code; it does not expose
numeric concurrency tuning as a user setting.

MinerU folder conversion uses the service health capability when the endpoint
reports `max_concurrent_requests`, otherwise it falls back to one request.
Semantic extraction starts with a conservative process-local window and grows
in bounded successful waves up to the number of pending segments. Provider
admission remains the final request fence, and a rate-limit response stops new
waves and enters the existing cooldown/recovery path.

Source iteration, factual publication, generated Markdown mutation, and
materialization remain deterministic and serial. Concurrency must not change
fact identity, merge order, source-level recovery, or visible output.

### R21. Authoritative Ingest Observability

The ingest report distinguishes semantic usage records from model-call
attempts, responses, failures, invalid outputs, and retries. Attempt counts and
observed peak in-flight calls come from the run event stream; configured
segment capacity comes from the immutable execution contract. Each processed
segment retains its own semantic usage and elapsed time. Missing telemetry is
reported as unavailable rather than zero. Every published source processing
record carries the owning attempt ID.

## User Scenarios

### Normal Desktop Ingest

The user submits local content, sees one task start, and receives a terminal
result only after committed facts have a reconciled local projection and index,
or receives an explicit materialization warning.

### CLI Ingest

The CLI submits and executes its task in the foreground using the same claim,
lease, factual commit, and materialization functions as the desktop process.
It does not create daemon threads that survive command completion.

### Application Crash

After restart, expired running attempts become `recovery_needed`; committed
facts remain visible; dirty or prepared materialization is completed without a
model call.

### Application Close During Provider Wait

The wait is interrupted, no attempt lease is claimed, and the task remains
queued for the next launch or explicit retry.

### Application Close During Model Work

No new model call starts after shutdown. If the current call cannot be
cancelled, its result cannot publish after its lease is relinquished. The task
is recoverable on next launch.

### Manual Page Edit

An edit made through KnoArbor acquires the vault write lock, writes atomically,
increments materialization epoch, and synchronously reconciles the machine
snapshot. A concurrent build cannot consume the refresh without producing a
successor epoch.

### External File Edit

Startup, explicit rebuild, or a machine-index freshness check detects a changed
wiki tree fingerprint. The resulting rebuild verifies that the fingerprint did
not change during scanning before publishing `CURRENT`.

## Public Contract Requirements

- Existing ingest submission request shapes remain unless a separate public
  contract migration is approved.
- `execution=queued` means scheduled in the current local application process;
  it does not promise work while the application is closed.
- Force reprocess always returns a new task and attempt identifier.
- Run list and read endpoints project SQLite attempts in one bounded query.
- `repair-derived-views` is replaced by a materialization rebuild operation.
  No hidden alias or fallback is retained in development builds.
- API and CLI cancellation call the same transactional service method.

## Acceptance Criteria

1. No production module named ingest runtime registry, ingest dispatcher, or
   derived dispatcher remains.
2. No empty background loop polls a vault database.
3. No workflow path reads JSON checkpoint, prepared, queue, or run-control
   files.
4. Closing the application during pause/provider wait leaves no live worker.
5. A process crash after task commit is recovered by the next startup scan.
6. A process crash after fact commit but before index publication is recovered
   without a model call.
7. A wiki mutation during index build causes a successor epoch or build retry.
8. Repeated force-reprocess invocations create distinct tasks and revisions.
9. Run listing executes a bounded bulk projection with no per-attempt store
   initialization.
10. Transactional source facts and current machine index survive migration from
    the current v4 development store.
11. The final implementation contains fewer runtime states, worker classes,
    renewal threads, and lines of ingest lifecycle code than the superseded
    implementation.
12. Replacing a full-source revision or deleting its Raw removes image assets
    owned only by inactive revisions while preserving every image referenced by
    another active revision.

### R20. Preprocessor Output Identity

Folder preprocessing MUST preserve each source's path relative to the selected
input root beneath the output directory. Two files with the same basename in
different source directories MUST produce distinct Markdown artifacts. A
single-file invocation keeps the direct `<stem>.md` output contract.

### R21. MinerU Readiness Authority

MinerU readiness diagnostics validate the configured endpoint required by the
current per-input workflow. They MUST NOT reject a valid configuration because
the retired persistent `input_dir` field is absent.

### R22. MinerU Native Transport

The production document processor MUST own a callable HTTP transport that sends
the configured file and multipart fields to the synchronous MinerU endpoint.
Tests MUST exercise that production transport boundary instead of replacing it
in every fixture.

### R23. MinerU Configuration Fidelity

Saving the UI configuration MUST preserve supported parse mode, canonical
backend, file patterns, recursion, response options, language list, page bounds,
and optional inference server URL. Supported backends are exactly `pipeline`,
`vlm-auto-engine`, and `hybrid-auto-engine`. Legacy `vlm-engine` and
`hybrid-engine` values MUST migrate to their official `*-auto-engine` names.
Any other backend MUST fail explicitly rather than being silently replaced
with `pipeline`.

### R24. MinerU Response And Readiness Safety

Diagnostics MUST distinguish a configured endpoint from a reachable MinerU
health endpoint. JSON and ZIP response modes MUST both materialize Markdown;
ZIP extraction MUST reject path traversal and symbolic links.

### R25. One Semantic Source Outcome

Successful deterministic compilation has one source outcome in both dry-run
and write execution. A source is `partial` and non-retryable when claim
candidates existed but none survived candidate-local grounding; otherwise it
is `processed`. A deterministic structural postcondition violation is a typed
internal `failed` result. The runtime has no source or segment `rejected`
state, approved-segment list, quality-gate payload, or compatibility fallback
that reinterprets those removed states.

### R26. Contained Immutable Input Generation

An immutable input generation identifier MUST use the canonical
`sha256:<64 lowercase hexadecimal>` form. Every manifest member path MUST be a
normalized relative path contained by that generation directory, and every
document payload MUST be included in the verified file inventory. Absolute
paths, parent traversal, empty members, and checksum-consistent manifests that
escape the generation directory fail input verification before execution.

### R27. Active-Revision Image Retention

Image retention follows active factual revision ownership. After a successful
full-source head replacement, including reingest or projection editing, images
referenced only by inactive revisions of that source MUST be removed. Purging a
Raw source MUST remove its unshared images. An image referenced by any active
revision MUST remain available, including a content-addressed file shared by
multiple sources.

Cleanup MUST derive candidates from persisted attachment `relative_path`
values, accept only paths contained by `raw/derived/assets/images`, and run
only after the source-head replacement or purge succeeds. It MUST NOT infer
ownership from filenames, sweep unrelated orphan files, delete non-image
assets, or change the attachment schema or asset layout. Inactive historical
fact JSON remains immutable but does not retain image files.
