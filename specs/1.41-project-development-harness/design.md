# 1.41 Project Development Harness Design

## Lifecycle And Decision

Accepted. The initial standard-library CLI becomes a repository-development
control plane. It remains outside the product package and combines tracked,
versioned method assets with ignored, Initiative-local execution records.

The design adopts the reference system's independent stage boundaries,
synchronous cognitive roles, low-frequency human authority, fixed gates,
baseline delta, visible soft scars, repository knowledge, delivery audit, and
evolution metrics. It adapts external delivery to GitHub and local handoff. It
rejects persistent Team Mode, Agent messaging, arbitrary command gates, and
business systems not used by KnoArbor.

## End-To-End Control Flow

```text
objective / GitHub issue / accepted SDD
  -> admission and manifest freeze
  -> Requirement role packet -> requirement artifacts
  -> human requirement decision
  -> current-state evidence when required
  -> Design role packet -> design and task artifacts
  -> human design decision when required
  -> independent design verdict or typed rollback
  -> workspace fingerprint + fixed baseline gates
  -> Implementer packet -> code, tests, verification references
  -> fixed integration gates
  -> read-only Reviewer packet -> verdict or typed rollback
  -> scope delta + acceptance gates + human acceptance when required
  -> idempotent local/GitHub delivery adapter
  -> portable handoff + metrics + immutable closure
```

The Controller determines the next legal transition and invokes deterministic
operations. Cognitive roles produce artifacts. Scripts validate state and run
gates. Humans own authority decisions. Adapters own external writes.

## Tracked Method Assets

Tracked assets use immutable version directories plus one current pointer:

```text
.codex/development/current.json
.codex/development/methods/v2/
  policy.md           authoritative run invariants
  controller.md       authoritative Controller transition procedure
  workflow.json       canonical stages, routes, human gates, rollback graph
  roles.json          role read/write/forbidden contracts
  artifacts.json      artifact kinds and producing/consuming stages
  gates.json          fixed gate catalog and route profiles
  project-map.json    path ownership and context sources
  delivery.json       supported adapters and side-effect classes
```

The JSON files use `knoarbor_development_method.v2`; the Markdown contracts have
fixed required headings. The pointer selects the default for new runs only. A
manifest pins method version `v2`, its repository-relative version directory,
and a SHA-256 digest of every bundle file. Version assets are immutable and
cannot be deleted while any open Initiative references them. Resume loads the
pinned directory rather than the current pointer. A method revision uses a new
directory such as `v2.1`; overwriting `v2` is governance failure.

### System Layers Versus Method Bundle

The six system layers are Policy, Operator Procedure, Roles, Workflow, Gates,
and Adapters.
They are the conceptual architecture, not a claim that exactly six files exist.
The immutable method bundle is the executable contract set listed above:
`policy.md`, `controller.md`, and six JSON files.

The CLI is the invocation surface and does not own in-flight rules. It loads
the pinned `controller.md` and role packet for an active Initiative. Policy
used by a run is the pinned `policy.md`; stable maintainer docs explain the
current method but are not runtime authority. A later CLI or maintainer-doc edit
therefore cannot change an old run.

## Initiative Records

Ignored execution state lives in `.codex/initiatives/<initiative-id>/`:

```text
manifest.json       immutable intent, method digests, scope, roles, budgets
checkpoint.json     current materialized state
events.jsonl        append-only transition and decision audit
baseline.json       regenerated Git/content baseline view
artifacts.json      regenerated artifact view
gates.json          regenerated gate view
decisions.json      regenerated human-decision view
delivery.json       regenerated delivery view
metrics.json        regenerated deterministic measurements
handoff.json        regenerated redacted portable summary
```

The checkpoint is the sole mutable execution-state authority and contains all
current stage, artifact, gate, decision, delivery, usage, and blocker state. The
event stream is audit evidence, not replay authority. Every other JSON view is a
disposable projection of checkpoint state. Feature `tasks.md` remains the
product-task authority.

### Transaction And Concurrency Boundary

Each Initiative has an advisory `writer.lock`. Every mutation:

1. acquires the single-writer lock with bounded timeout;
2. validates method digests, checkpoint revision, and event tail;
3. computes one transition with `revision = previous + 1`, including every next
   stage, artifact, gate, decision, delivery, usage, and blocker value;
4. writes that complete next checkpoint to a temporary file and fsyncs it;
5. appends one canonical event containing revision, previous event hash, payload
   digest, and event hash, then fsyncs it;
6. atomically replaces the checkpoint with the prepared revision and fsyncs the
   run directory.

The prepared checkpoint is the only current-state publication and contains the
expected event hash. Auxiliary views may be absent or partially written without
affecting recovery because they are regenerated after commit. Startup handles only
two recoverable cases: an event at `checkpoint.revision + 1` whose prepared
checkpoint is present is finalized; a prepared checkpoint without its event is
discarded. Any other gap, duplicate revision, or hash mismatch quarantines the
run at `awaiting_human`. Tests inject crashes after every write/fsync/replace
boundary and race two processes for the lock.

## Workflow State Machine

Each stage record contains status, attempt, responsible role, entry/resolution
timestamps, accepted artifact IDs, decision ID, gate IDs, skip type, blocker,
and rollback source. Status is:

```text
pending | running | passed | skipped | rejected | failed | awaiting_human
```

Only the current stage can start or resolve. `approve` resolves a human stage.
`reject` records a decision in the same revision transaction, validates the requested rollback against
`workflow.json`, increments consecutive rejection count, and resets the rollback
target plus all downstream stages to pending while preserving prior attempts in
events. Three consecutive rejections pause the target at `awaiting_human`.

A successful Reviewer verdict resets consecutive review-rejection count. Required stages cannot
be skipped. Conditional skips use catalogued types such as `not_bugfix`,
`no_public_or_cross_owner_change`, `fast_route`, or `existing_equivalent_evidence`.

Closure is available only through `close`. Repeated closure validates existing
evidence but does not repeat implementation, delivery, or notification.

## Artifact Contract

Artifact metadata is a typed collection inside checkpoint and has a regenerated
view:

```json
{
  "artifact_id": "requirement-analysis:requirements:1",
  "storage_class": "repository_ref",
  "kind": "requirements",
  "stage": "requirement_analysis",
  "producer_attempt": 1,
  "producer_role": "requirement",
  "path": "specs/1.41-project-development-harness/requirements.md",
  "sha256": "...",
  "input_artifacts": [],
  "status": "accepted",
  "invalidated_by_event": null,
  "accepted_at": "..."
}
```

`repository_ref` paths are repository-relative and must be inside the manifest
allowlist or an explicit read-only input set. Content is never copied. A
`control_record` has no path and contains only schema-bounded fields such as
outcome, finding IDs, rollback target, and sanitized rationale; it cannot hold
arbitrary prose, source, or command output. Before entering a later stage the CLI
re-hashes all declared repository inputs. Changed accepted input blocks the
transition and requires rollback to its owner.

Rollback walks the artifact dependency graph and changes affected artifacts
from `accepted` to `invalidated`, recording the rejecting event. Historical
metadata remains addressable by attempt but role packets include only accepted
artifacts from the current dependency closure. A `task_plan` artifact is only a
reference to the owning feature spec's `tasks.md`; the Harness cannot create a
second task list.

Artifact kinds include objective, requirements, acceptance criteria, impact
map, reproduction, design, task plan, verification plan, implementation,
tests, integration evidence, design verdict, code verdict, acceptance verdict,
delivery evidence, and handoff.

## Role Packets And Isolation

`role-packet` derives a minimal JSON packet from the manifest, current stage,
role contract, project map, and accepted artifact references. It includes:

- objective and non-goal references;
- readable artifact paths and digests;
- required output kinds;
- allowed repository write paths;
- forbidden actions and side effects;
- validation and rollback targets;
- remaining call and retry budgets.

Requirement, Design, Implementer, and Reviewer use synchronous invocations. The
Harness does not maintain a Team or mailbox. Role execution identity is recorded
for each submission. Reviewer packets have an empty repository write allowlist.
The Reviewer returns a structured verdict to the Controller; the Controller
persists it as a `control_record` inside checkpoint in the same revision
transaction. Any repository mutation during review blocks verdict acceptance.

The Harness enforces artifact and workspace consequences. It does not claim to
authenticate a model process; the Controller Skill must invoke distinct
execution identities where required.

## Human Decision Contract

Human decisions use explicit commands or equivalent structured UI actions:

```text
approve <initiative> --stage requirement_confirmation --actor <human>
reject  <initiative> --stage independent_code_review --to implementation ...
```

Each decision records stage, decision, human actor, reason, timestamp, and
rollback target. Free-form semantic guessing is not part of the deterministic
CLI. A conversational Controller may translate natural language into one of
these explicit operations only after presenting the exact decision.

Human gates are:

- requirement confirmation for standard and strict;
- design confirmation for strict and catalogued public/cross-owner changes;
- final acceptance when external delivery, release, destructive operation, or
  an unresolved soft scar requires human authority;
- circuit-breaker recovery after three consecutive rejections or budget
  exhaustion.

## Workspace Baseline And Scope Delta

The workspace baseline records branch, HEAD, relative repository identity,
method digests, allowed paths, and SHA-256 fingerprints for tracked and
non-ignored untracked files. Symlinks hash their target text. Missing tracked
files use a typed sentinel.

Post-baseline scope delta compares path-to-fingerprint maps. A pre-existing
dirty path is tolerated only while unchanged. The Harness never resets, cleans,
stages, commits, or rewrites an out-of-scope path.

Reviewer entry adds a review snapshot. Reviewer completion verifies that no
repository file changed during the read-only review. The verdict is a
Controller-persisted control record and creates no repository exception.

## Fixed Gate Catalog

`gates.json` owns stable gate IDs, severity, command templates, phases, routes,
conditions, timeout, and scar policy. Version 2 does not accept a command from
Initiative input.

Initial catalog:

| Gate | Severity | Boundary |
| --- | --- | --- |
| `affected-validation` | hard | scoped Ruff, architecture, docs, focused tests |
| `artifact-consistency` | hard | SDD lifecycle, tasks, artifact digests |
| `secret-scan` | hard | changed scope and portable evidence |
| `development-suite` | hard, conditional | full local deterministic development gate |
| `full-chain-focused` | hard, conditional | affected real product journey |
| `renderer-interaction` | soft/conditional | changed renderer behavior |
| `desktop-contracts` | hard/conditional | desktop or packaging boundary |
| `live-model-local-observation` | soft/conditional | local semantic quality observation |
| `live-model-release` | hard/conditional | release semantic quality boundary |

Route profiles select the minimum catalog set and freeze each effective gate ID,
severity, condition, and phase at admission. The manifest may add catalogued
gates but cannot remove a route-required gate. Gate commands execute without a
shell and receive only validated placeholders.

All subprocess output passes through one output proxy. It captures a
bounded buffer, redacts credential patterns, configured repository/user paths,
environment-value matches, and source-like lines, then displays only gate ID,
exit class, duration, counts, and sanitized diagnostic locations. Raw output is
discarded. Version 2 has no raw-output or debug-output mode.

`output_fingerprint` is derived from a canonical diagnostic projection, never
from the raw byte buffer. The projection keeps stable failure/error headers,
diagnostic codes, assertion/error classes, and repository-relative locations;
it drops progress lines and normalizes volatile runtime values before hashing.
If a failing command exposes no recognized diagnostic record, the projection
hashes the complete sanitized non-log set and retains a bounded sanitized tail,
so differences outside that tail do not collapse opaque failures into one
identity. Tests cover identical failures with different
timestamps/temp paths/run IDs and changed test or diagnostic identities.

Acceptance compares equal gate identities between A and B. Unbaselined,
missing, severity-changed, or newly failing hard gates block. Identical failures
remain visible. Soft failures require complete scars and propagate into verdict,
handoff, delivery, and metrics.

## Project Context And Portfolio

`project-map.json` maps repository path prefixes to owning specs, stable docs,
entry points, test families, and escalation Skills. `context` combines this map
with current registry records, Git state, the Initiative scope, accepted
artifacts, and related local Initiative summaries. It stores no source content.

`portfolio` derives active Initiative ID, route, current stage, blockers,
updated time, and artifact references from local records. It is a navigation
view, not a second task ledger. `handoff` exports the same control facts without
absolute paths so a pull request, issue, or another machine can carry them.

Cross-machine `export-bundle` is allowed only at a Git-backed handoff checkpoint:
the repository has an exact commit OID, every accepted repository artifact
matches that tree, and the OID is reachable from the declared remote. The bundle
contains normalized `control_record` bodies, method identity, repository
artifact paths/digests, and the OID, but no repository artifact bodies.
`import-bundle` requires a repository checkout containing
that OID, verifies the bundle root hash and every artifact digest, rejects a
conflicting local Initiative ID, and creates a new local lock domain. Arbitrary
dirty-worktree transfer is explicitly unsupported.

## Delivery Adapters

Delivery is a typed substate owned by `closure`:

```text
not_started | intent_recorded | delivered | failed | awaiting_human
```

External operations are legal only while `closure` is `running`, acceptance is
passed, and delivery is not yet `delivered`. Failure leaves acceptance unchanged
and keeps closure `running` for retry or moves it to `awaiting_human` when its
budget/circuit breaker is exhausted. Closure cannot pass until required delivery
is `delivered`.

Version 2 adapters are:

- `local`: generate and validate a portable delivery bundle with no external
  write;
- `github`: create or reuse a pull request through `gh` only when `github_pr`
  is authorized in the manifest.

GitHub delivery admission requires a sealed acceptance snapshot, a commit OID
matching that snapshot, a clean delivery tree, a declared base/head ref, and a
remote head OID equal to the accepted OID. Commit and push remain explicit human
or separately authorized Git operations; the adapter blocks until their facts
are true.

The idempotency identity is `(repository, base ref, head ref, accepted head OID,
Initiative marker)`. Before a write, the Controller durably records a delivery
intent and idempotency identity inside checkpoint. The adapter queries existing PRs by head/base
and verifies the marker and head OID. A closed or merged PR is reusable evidence
only when the accepted OID matches exactly; branch reuse or a moved head blocks
and requires a new branch. After lookup/create it records an outcome in a new
revision. On restart, an intent without outcome always repeats lookup before any
write, closing the remote-success/local-crash ambiguity.

Creation uses argument arrays, not a shell, and never reads credentials itself.
It records remote identity, URL, OID, attempt outcome, timestamp, and redacted
error class. Optional issue mutation and notification remain deferred.

Required delivery operations block truthful delivery. Optional notification
failures may be scars. A network failure never rewrites earlier stage success.

## Metrics And Evolution

`metrics` deterministically derives:

- elapsed and active duration by stage;
- attempts, rejections, rollback targets, retries, and circuit breaks;
- Agent calls and human decisions;
- gate passes, pre-existing failures, new failures, and soft scars;
- changed paths and scope overflow;
- delivery attempts, reuse, success, and failure;
- total cycle time when closed.

`portfolio --metrics` aggregates only non-sensitive counts and durations across
local runs. Workflow changes use these results and update method assets only for
new Initiatives. The first maturity review occurs after five real runs; no fixed
performance target is invented before then.

## Security And Privacy

- Method assets contain no credentials or user-specific absolute paths.
- Initiative records reject credential-like strings.
- Portable handoff replaces repository root with a repository/remote identity.
- The output proxy prevents raw command output, prompts, source contents,
  environment values, credentials, and private paths from entering either
  persisted records or normal terminal/session output.
- External tools inherit credentials from their normal environment; the Harness
  neither reads nor prints them.
- Delivery side effects require explicit manifest authorization and stage
  eligibility.

## Compatibility And Migration

The existing v1 format has no accepted production runs. Version 2 rejects v1
runs with a migration message; it does not guess missing role, artifact, gate,
decision, or method-digest state. A maintainer may keep v1 test fixtures as
historical evidence, but real work starts a new v2 Initiative and baseline.

The CLI path remains `scripts/project-development-harness.py`. Internal modules
may move under `scripts/development_harness/`; no shipped Python API is created.

## Reference Mechanism Decisions

| Reference mechanism | Decision | KnoArbor adaptation |
| --- | --- | --- |
| Thirteen-stage relay | adopt | retain distinct failure/rollback boundaries |
| Four cognitive roles plus Controller | adopt | synchronous role packets, no persistent team |
| Five human checkpoints | adapt | requirement, conditional design, acceptance, circuit breaker |
| Seven fixed gates | adapt | map to current Python/renderer/desktop/full-chain/release owners |
| Baseline B-A and soft scars | adopt | fixed gate IDs plus content scope delta |
| Repository navigation map | adopt | tracked owner/path/test map, generated fresh context |
| Cross-requirement board | adapt | derived portfolio and portable handoff, no duplicate tasks |
| TAPD/iWiki/worker messaging adapters | reject | unused business systems |
| Git hosting delivery | adapt | bounded GitHub adapter through `gh` |
| Team Mode and Agent mailbox | reject | synchronous calls avoid lifecycle deadlock |
| Arbitrary shell gate commands | reject | catalog commands execute without a shell |

## Rejected Alternatives

- **Keep the v1 recorder and rely on Skill prose:** cannot enforce artifacts,
  rollback, gate identity, delivery, or metrics.
- **Create a second total-system spec:** duplicates the existing 1.41 owner.
- **Track every run in Git:** produces merge conflicts and a second noisy task
  ledger. Portable summaries attach to existing delivery authorities instead.
- **Use hidden Agent memory as project knowledge:** not auditable or shared.
- **Let downstream roles repair upstream artifacts:** destroys responsibility
  and acceptance provenance.
- **Make every gate hard:** creates bypass pressure and confuses quality signals
  with release red lines.
- **Automatically commit, push, or release:** exceeds normal implementation
  authority and makes recovery unsafe.
- **Add generic HTTP/OAuth adapters:** expands credentials and audit paths; use a
  named delivery adapter only when the repository actually needs it.

## Evolution Rule

Method assets are immutable, version-addressable, and pinned per Initiative. A
completed run never changes its own rules; an old open run continues loading its
pinned version after the current pointer advances. The current pointer and
project Skills may advance, but an old run loads authoritative policy and
Controller behavior from its pinned method bundle. Stage merging, parallel
Agents, new external writes, gate severity changes, or automation of a human
decision require new evidence and an accepted 1.41 revision.
