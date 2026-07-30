# 1.37 Local-First Ingest Simplification Design

## Status

Accepted target design for local ingest execution, crash recovery,
materialization, index publication, and knowledge revision. Implementation
remains pending against the KnoArbor 2.3.1 baseline.

## Decision Summary

KnoArbor will use a local-operation architecture rather than a durable worker
service architecture.

The system keeps the mechanisms required for local crash consistency:

- immutable input generations;
- SQLite task and attempt state;
- attempt lease and epoch fencing;
- atomic source revision transactions;
- one cross-process vault write lock;
- one materialization epoch state;
- immutable index generations and atomic `CURRENT`;
- startup reconciliation and migration journal.

The system removes mechanisms whose only purpose was online-service behavior:

- persistent ingest and derived polling workers;
- runtime and dispatcher registries;
- wake generations and reliable in-memory notification concerns;
- source-projection and vault-index job queues;
- derived leases and renewal threads;
- segment-result and prepared-result recovery caches;
- run JSON as cancellation or workflow control;
- direct transactional index publication outside the materializer.

The accepted fact-layout amendment does not add a lifecycle owner. It replaces
the revision file shape and physical path through the existing
`IngestExecutionSession -> storage.source_revisions -> TransactionalIngestStore`
publication boundary.

## Factual Revision Publication Amendment

The publication sequence is:

```text
PublishedKnowledgeRevision.v2
  -> stage .knoarbor/facts/.staging/<random>/
       source.json
       knowledge.json
       diagnostics.json
       manifest.json
  -> verify schemas and hashes
  -> atomic rename to facts/<source-key>/<revision-key>/
  -> SQLite transaction selects revision and requests materialization
```

`source-key` and `revision-key` are deterministic typed identity encodings.
An already existing target with the same verified manifest is idempotent. An
existing target with a different manifest is an integrity failure. A staged or
renamed directory that is not selected by a source head remains unreachable and
is reclaimed by startup reconciliation.

The materializer resolves active source heads, verifies each manifest, reads
`source.json` and `knowledge.json`, and renders projections and indexes.
`diagnostics.json` is available for audit but is not a materialization input for
ordinary page or retrieval facts.

### Migration

The bounded startup scan detects legacy manifest paths. Under the vault lock it
validates each manifest, converts payload schemas, writes and verifies the
deterministic target, then switches the revision manifest path transactionally.
The manifest path itself is the migration marker, so no second migration state
is introduced. Restart repeats only legacy rows and can adopt a fully verified
target left by a crash after rename. After all revisions are converted, it
removes legacy generation and staging directories. No semantic provider is
available to migration code.

## Architecture

```text
Desktop / loopback API / CLI
          |
          v
IngestApplicationService
  resolve -> submit -> schedule/run task
          |
          v
TransactionalIngestStore ---- StartupReconciler
  task / attempt / facts        one scan on launch
  cursor / materialization
          |
          v
IngestTaskExecutor
  admission -> claim -> IngestExecutionSession
                         model -> factual commit
          |
          v
VaultMaterializer
  project pages -> stage index -> publish CURRENT
```

There are five owning components. Adapter code may not add a sixth lifecycle
owner.

## Component Ownership

### IngestApplicationService

Owns the public use case:

1. resolve request and freeze input generation;
2. build immutable execution command;
3. submit task;
4. schedule the task in the desktop operation executor or execute it in the CLI
   foreground;
5. project the resulting attempt for API/CLI/UI.

It does not own claims, leases, model policy, file writes, or recovery logic.

The persisted command schema is `ingest_execution_command.v2`. It records the
resolved absolute `vault_path`, the vault identity fence, and an optional
`vault_id`. Profile-selected commands reload by ID and verify the recorded path;
explicit-path commands reload by their recorded path and keep `vault_id` null.
There is no v1 runtime fallback.

### TransactionalIngestStore

Owns all durable workflow decisions:

- task and attempt creation;
- command idempotency or forced invocation identity;
- pause and cancellation;
- attempt claim, renewal, finish, and expiry normalization;
- source revision/head/cursor transaction;
- materialization epoch and publication phase;
- bulk run projection queries;
- migration journal.

The store exposes use-case methods rather than tables to adapters.

`runtime.transactional_ingest` remains the lifecycle authority. Its format
migration preflight may call leaf storage integrity readers, but it must not
import aggregate revision-publication or machine-index writer modules. Revision
manifest verification belongs to `storage.revision_integrity`; immutable
machine-index generation lookup and verification belong to
`storage.index_snapshot`. These readers do not import the transactional store
and do not create an additional lifecycle owner.

### IngestTaskExecutor

Executes one persisted task id. It has no queue loop.

1. load and verify command and input generation;
2. wait for provider admission without a task lease;
3. atomically claim the attempt;
4. process ready immutable sources concurrently while retaining deterministic
   source and segment result order;
5. renew before each model call and before each factual commit;
6. commit successful sources individually;
7. invoke materialization once after source processing;
8. finish attempt.

The executor receives one `OperationCancellationToken` combining user cancel
and application shutdown. It never reads a run file.

### VaultMaterializer

Owns all generated Markdown reconciliation and machine-index publication for a
transactional vault. It executes synchronously in the calling operation or
during startup reconciliation. It has no worker thread and no job lease.

Each call consumes at most one requested epoch. If local files or the requested
epoch change during the build, it leaves materialization dirty for the next
bounded operation instead of spinning internally.

### IngestExecutionSession

Owns the mutable attempt lease for one claimed execution. The pipeline sees
only `IngestExecutionPort`: renew before a model call and publish one factual
commit. It cannot construct a store, reconstruct a lease from monitor metadata,
or publish revisions directly.

### StartupReconciler

Runs once for configured vaults after application startup:

1. finish an idempotent migration phase if needed;
2. normalize expired attempts;
3. reconcile prepared or dirty materialization;
4. optionally schedule queued tasks according to local startup policy;
5. remove unreachable staging directories and index generations before readers
   or queued work are admitted.

It exits after the bounded scan.

## Local Execution Model

### Desktop And Loopback API

The desktop-owned local service has one process-level operation executor. It is
not vault-scoped and does not poll. Submission calls `executor.submit` exactly
once after the SQLite transaction commits.

If the process crashes between commit and submit, the queued task remains in
SQLite and the next application startup finds it. The product does not promise
that another already-running process will discover it immediately.

### CLI

The CLI submits, then calls `execute_task(task_id)` in the foreground. A second
local process may race for the task, but SQLite claim permits only one owner.
No registry or daemon thread survives command exit.

### Application Shutdown

The operation executor closes admission and signals all operation tokens.

- pre-claim wait returns with the task queued;
- running execution stops scheduling model calls;
- current uncancellable HTTP call may finish, but publication still requires a
  valid attempt lease and cancellation check;
- a task not completed within the bounded shutdown grace period is atomically
  moved to `recovery_needed` by its owner;
- shutdown joins owned threads and fails loudly if a thread remains alive.

No `join(timeout)` result may be ignored.

## Task And Attempt State

### Task State

```text
queued
  -> running
  -> completed | partially_failed | failed | cancelled | recovery_needed

recovery_needed | failed | partially_failed
  -> queued (new attempt under same command)
```

Only interrupted attempts, provider rate limits, and failures persisted as
retryable may take the recovery transition. `TransactionalIngestStore` owns
both the assessment and admission decision; API presentation does not infer a
second recovery policy.

Provider pause, capacity, and cooldown do not require a separate durable
`waiting_admission` state. The attempt may report an admission stage while its
durable state remains `queued`. No running lease exists before claim.

### Attempt Lease

`AttemptLease` remains because desktop and CLI are separate local processes.
It contains task id, attempt id, epoch, and expiry. Every factual commit and
finish validates current attempt, epoch, expiry, and cancellation.

There is no autonomous renewal thread. The executor renews:

- immediately before a model request;
- after a model response;
- before a factual commit;
- before any long deterministic phase whose bound approaches lease expiry.

The lease duration must exceed configured request timeout plus a fixed local
commit margin.

### Attempt Completion And Materialization Failure

Attempt terminal state describes source execution, not rebuildable view health.
A successful factual attempt may finish `completed` while materialization is
dirty or failed, but the public composite state remains
`materialization_pending` rather than fully visible. `partially_failed` is
reserved for source execution failures. Retrying materialization never creates
an ingest attempt or invokes a model.

The application normally reconciles before returning a completed direct or CLI
operation. If reconciliation fails, committed facts remain successful and the
user receives an explicit rebuildable-view warning.

Page readers preserve this distinction: while active facts exist and
materialization is not clean, an absent projection is reported as
`materialization_pending`, not as authoritative page deletion.

### Force Invocation

Normal submission is idempotent by immutable command hash. Force submission
creates an explicit invocation id before task hashing:

```text
force_invocation_id = uuid
```

The id is part of task identity and factual input revision identity. Recovery
does not create a new force invocation id.

## Input And Source Recovery

Input generation remains content-addressed and verified. This is useful even in
a local app because a source file may change after submission or before crash
recovery.

The generation ID has one canonical `sha256:<64 lowercase hexadecimal>` form.
The reader resolves every manifest member as a normalized relative path beneath
the selected generation directory, verifies that every document belongs to the
hashed file inventory, and rejects absolute paths, parent traversal, and
checksum-consistent path escapes before returning any source document.

The base architecture recovers at source boundary:

- committed source revision key -> skip model work;
- no committed revision -> repeat that source's model work;
- partial segment results -> discarded with the failed attempt.

The source revision key contains the factual contract hash, raw source
identity, raw revision identity, optional session window, and force invocation
identity. It deliberately excludes the enclosing input generation so an
unchanged source in a changed multi-source generation skips model work.

This accepts possible repeated model cost in exchange for one factual recovery
authority. Segment caching may return only through a later independent spec
with measured product need and a content-addressed artifact contract.

Semantic execution exposes only `processed`, `partial`, or `failed` source
outcomes. Dry-run and write execution calculate the same candidate-local
outcome before publication. All-candidate rejection is `partial` and
non-retryable; compiler-integrity failure is typed `failed`. No source or
segment `rejected` state, quality gate, approved-segment list, or compatibility
adapter remains.

## Factual Transaction

For one successful source, one SQLite transaction validates the attempt lease
and commits:

- immutable source revision metadata;
- source head or contiguous session watermark;
- source cursor;
- entity contribution replacement;
- materialization `requested_epoch + 1`;
- requested fact generation.

Immutable fact files are staged and hashed before this transaction. If the
transaction fails, their unreachable generation is removable. No generated
Markdown or index work occurs inside the factual transaction.

## Materialization Model

### Schema

Each vault has one row:

```text
materialization_state
  singleton                   = 1
  requested_epoch             integer
  published_epoch             integer
  requested_fact_generation   text
  published_fact_generation   text nullable
  prepared_index_generation   text nullable
  prepared_wiki_fingerprint   text nullable
  phase                       dirty | building | prepared | clean | failed
  error                       text nullable
  updated_at                  real
```

`requested_epoch` is a monotonic local mutation clock. It advances for:

- factual source commits;
- application-controlled page writes/deletes/renames;
- explicit materialization rebuild;
- detected external wiki changes.

It is not derived solely from fact generation, so manual wiki refreshes cannot
coalesce into an already-running build unnoticed.

### Reconciliation Algorithm

```text
repeat:
  acquire VaultWriteLock
  resume prepared publication if present
  read token = requested_epoch + requested_fact_generation
  if token already published and wiki fingerprint unchanged: return clean
  set phase=building for token
  atomically rewrite generated source projections
  fingerprint wiki tree before index scan
  build immutable index generation in staging
  fingerprint wiki tree after index scan
  if fingerprint changed: discard generation, increment request epoch, return dirty
  verify index generation
  persist phase=prepared + generation id + token + fingerprint
  atomically replace CURRENT
  transactionally mark token published
  if requested_epoch advanced while building: return dirty
  otherwise mark clean and return
```

The vault lock serializes KnoArbor-controlled local mutations. The double
fingerprint detects an external editor that does not honor the lock.

An external edit after the second fingerprint is a later local mutation and is
picked up by the next startup, explicit rebuild, file-watch notification, or
freshness check. The design does not claim atomic coordination with an editor
that does not participate in KnoArbor's lock.

### Crash Boundaries

| Crash point | Durable result | Startup action |
| --- | --- | --- |
| Before facts commit | No new source head | Reprocess source |
| After facts commit | Dirty epoch | Reconcile without model |
| During projection writes | Dirty/building | Rewrite projections |
| During index staging | Invisible staging | Remove and rebuild |
| After prepared phase | Verified generation id | Publish CURRENT idempotently |
| After CURRENT switch | Prepared or clean | Verify pointer and mark clean |
| New epoch during build | Requested > published | Build successor |

Generated Markdown remains a rebuildable local view and may be temporarily
partially updated after a process crash. Machine readers use only immutable
index snapshots; factual readers use committed source revisions.

## Machine Index Boundary

Transactional vault publication is capability-based:

- only `VaultMaterializer` can call the internal CURRENT switch;
- migration can call a separate journal-bound resume function;
- vault initialization creates the v5 store and invokes the same materializer.

The raw pointer-switch function is private to `storage/wiki_index.py`. Public
callers request materialization; they cannot pass a string flag to simulate a
capability.

Index generation identity includes deterministic artifacts, requested fact
generation, and captured wiki fingerprint. Readers resolve CURRENT once and
verify all artifacts before use.

At application startup, after materialization recovery and before request or
queued-work admission, generations not referenced by CURRENT, published state,
or prepared state are removed. Runtime publication never prunes snapshots, so
cleanup remains confined to the pre-admission startup phase.

## Knowledge Revision Integration

The execution port receives linked revision drafts only after 1.26 source
validation and 1.27 canonical identity linking. The factual transaction
persists the processing record, source entity contributions, canonical
entities, claims with entity IDs, relations with canonical endpoint and
supporting-claim IDs, synthesis, evidence, and bounded revision diagnostics.

The transaction does not reconstruct contributions from display entities or
repeat semantic validation. It owns revision identity, manifest integrity,
active-head fencing, cursor/contribution publication, and materialization
request.

`VaultMaterializer` reads only active published revisions. One build uses one
fact-generation token and renderer version, creates readable projections and
the machine-index generation, validates both, publishes the index pointer, and
then marks the epoch clean. Canonical content uses revision metadata rather than
current time.

## Composite Completion State

Public presentation combines attempt, factual, and materialization state:

```text
processing
  -> failed_before_commit
  -> facts_committed / materialization_pending
  -> visible
  -> partially_visible
```

A factual commit is not rolled back because a rebuildable view failed, but the
operation is not presented as fully visible until materialization is clean.

Recovery commands are explicit:

- `retry_processing`: creates a new attempt and may call the model;
- `rebuild_projection`: reads facts without an attempt or model call.

## Run Observation

SQLite attempts are bulk-projected with one bounded query joining tasks and
attempts. Filtering, ordering, and limit happen in SQL. Run JSON and JSONL may
supplement live progress and event history for the selected rows only.

Cancellation is written to SQLite first and observed through the operation
token/store. A run file cannot cancel ingest.

## Provider Admission

Provider admission stays local and simple:

- process-local semaphore limits concurrent requests in the desktop process;
- CLI has its own process-local limit;
- cooldown deadline may remain in local app data for cooperation across local
  processes;
- task claim occurs only after admission;
- application shutdown and user cancellation interrupt every wait.

The request limit is explicitly process-local. A cross-process global request
scheduler is outside this spec.

Numeric concurrency is not a public configuration contract. The immutable
execution contract records the effective policy selected at admission:

- semantic segment execution starts at two concurrent calls when at least two
  segments are pending;
- each fully successful wave admits one additional pending call;
- the structural ceiling is the number of segments in that source, so there is
  no unrelated fixed maximum such as eight;
- merge order remains source segment order regardless of completion order;
- a provider rate limit prevents another wave and uses the existing durable
  cooldown and source-level recovery path.

Document conversion has a different capacity owner. Folder conversion probes
the configured MinerU `/health` endpoint and uses its positive
`max_concurrent_requests` value, bounded by the number of pending rich files.
If the endpoint does not publish the capability or cannot be probed, conversion
uses one request. Each converted document must be frozen before it enters the
semantic ready queue; ready documents may execute concurrently, while MinerU
continues producing later documents. MinerU conversion and model requests do
not share a semaphore, and completion order never determines input generation,
result, merge, or publication order.

### Ingest Report Measurement Authority

The report has two distinct measurement authorities. Semantic usage summaries
own token and provider-returned timing fields. The append-only run event stream
owns attempted calls, responses, failures, invalid-output retries, and observed
peak in-flight calls. Segment results retain the usage summary returned by
their own compile operation before deterministic merge. Publication copies the
attempt ID into `SourceProcessingRecord.run_id`; report construction never
reconstructs it from a path or latest-run lookup.

## Migration To `transactional_ingest.v5`

Migration runs under the cross-process migration lock and uses the existing
migration journal pattern.

### Preflight

- verify current v4 schema and source revision files;
- verify CURRENT if present;
- reject another live local process holding the vault write lock;
- classify tasks and attempts;
- compute active fact generation and wiki fingerprint.

### Database Commit

One `BEGIN IMMEDIATE` transaction:

1. creates `materialization_state`;
2. maps any queued/running/failed/blocked derived job to one dirty epoch;
3. converts expired running attempts to `recovery_needed`;
4. preserves queued attempts and immutable commands;
5. records v5 migration phase `db_migrated`;
6. drops `derived_jobs` and `segment_results`;
7. advances format to v5.

### Filesystem Cleanup And Publication

- remove old segment/prepared directories and unreachable staging;
- keep verified immutable input and source revision generations;
- retain CURRENT only if its fact generation and wiki fingerprint match;
- otherwise reconcile materialization;
- record migration `complete` only after publication is stable.

Startup resumes `db_migrated` idempotently. Runtime contains no v4 fallback
branch after migration.

## Public Surface Changes

- `repair-derived-views` becomes `rebuild-materialization`.
- The corresponding API route becomes `/ingest/materialization/rebuild`.
- Old development-only repair names are removed rather than aliased.
- `force_reprocess` retains its external name but always creates a new task.
- `queued` documentation states that execution requires the local application
  process to remain open, with startup recovery after interruption.

## Required Deletions

- `runtime/ingest_runtime.py`;
- `runtime/ingest_dispatcher.py`;
- `runtime/derived_dispatcher.py`;
- `storage/derived_views.py` job-drain API;
- `derived_jobs` table and `DerivedJobLease`;
- `segment_results` table and related retention policy;
- persistent worker lifecycle tests;
- wake-generation and worker-registry tests;
- direct public transactional index publisher;
- JSON-based ingest cancellation/control paths;
- obsolete derived-view repair CLI/API contract.

## Rejected Alternatives

### Keep Persistent Workers And Fix Shutdown

Rejected because no product requirement needs work while the app is closed or
continuous queue discovery. It preserves the source of lifecycle complexity.

### Keep Per-Source Derived Outbox

Rejected because a local vault can reconcile one final generation after facts
commit. Per-job leases, blocked index states, and coalescing are unnecessary.

### Keep Segment Results As An Optimization

Rejected for the base design. It adds a second execution-result lifecycle before
the product has established that repeated uncommitted model calls are an
unacceptable cost.

### Publish Index Directly After Every Write

Rejected because crash-safe CURRENT publication still needs a prepared phase
and successor detection. One materialization state provides that without a job
queue.

### Assume Exactly One Process

Rejected because desktop and CLI can overlap. SQLite claim and one OS file lock
are inexpensive local safeguards and remain necessary.

## Complexity Budget

Implementation is rejected if it violates any of these constraints:

- at most five ingest lifecycle owners named in this design;
- one task lease type and no derived lease type;
- no empty polling thread;
- no vault-scoped runtime registry;
- no more than seven durable task terminal/non-terminal states;
- one materialization row per vault;
- no workflow JSON reader;
- no per-segment durable recovery state;
- one public ingest application service used by API and CLI;
- one internal machine-index CURRENT switch owner.

## MinerU Source Identity And Readiness

The folder runner passes its selected input root into the document processor.
The processor derives an output path from the source-relative parent plus the
source stem, creating parent directories as needed. Direct file calls omit that
root and retain the flat output name.

`MinerUDocumentProcessor` owns the synchronous `/file_parse` HTTP transport.
Multipart booleans use lowercase strings, list fields repeat their form key,
and the uploaded file carries its detected media type. The adapter accepts the
native `results.<name>.md_content` JSON shape and ZIP output. ZIP members are
validated before extraction and Markdown selection remains bound to the
submitted source stem. Loopback and private-address MinerU endpoints bypass
environment HTTP proxies so a desktop proxy cannot intercept the local service.

Configuration diagnostics derive `/health` from the configured service origin
and distinguish `ready`, `endpoint_missing`, and `endpoint_unreachable`.
Input selection remains operation-owned and therefore is not configuration
readiness state. The configuration form preserves supported MinerU fields;
the only backend values sent to MinerU are `pipeline`, `vlm-auto-engine`, and
`hybrid-auto-engine`. Legacy `vlm-engine` and `hybrid-engine` values migrate
once to their official `*-auto-engine` names; other values fail validation.

Preprocessing remains part of immutable input generation before task
submission. Moving it inside an ingest attempt would change the admitted-input
and recovery contracts and is outside this patch.

## Active-Revision Image Cleanup

`storage.source_revisions` owns image reachability because it already owns
factual publication and can read the persisted `SourceProcessingRecord`
attachment inventory. A full-source publication captures the previously active
revision before the source-head transaction. Only after a new revision is
successfully selected does it use attachment paths from inactive revisions of
that source as cleanup candidates.

The page deletion service uses the same storage helper: it captures attachment
paths from every registered revision of the source, commits `purge_source`,
removes the fact directories, and then releases candidates. Session-window
publication does not supersede earlier active windows and therefore does not
produce cleanup candidates.

Reachability is path based and conservative:

1. accept only image attachments with a normalized relative path;
2. resolve only paths contained by `raw/derived/assets/images`;
3. build the protection set from all SQLite-selected active revisions;
4. unlink only candidate files absent from that protection set.

This targeted pass is not a vault-wide garbage collector. It does not infer
source ownership from a filename, scan arbitrary assets, or alter directories.
Historical inactive fact generations remain immutable and readable as records,
but their attachment metadata is archival provenance rather than an asset
retention root. Content-addressed images shared by two active sources remain
protected until the last active reference is replaced or purged.

Cleanup follows the existing vault write lock used by ingest publication,
projection editing, and page deletion. A failed publication never reaches the
cleanup step. An idempotent publication that resolves to an existing revision
does not displace a source head and therefore does not clean assets.
