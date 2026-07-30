# 1.41 Project Development Harness Requirements

## Lifecycle And Ownership

Accepted. This specification owns the repository-development control plane for
one bounded Initiative: admission, role handoffs, stage state, human decisions,
artifact integrity, workspace and gate baselines, project context, delivery
evidence, operational metrics, and recoverable closure.

Neighboring owners remain:

- feature specifications own product requirements, design, tasks, and feature
  verification;
- `docs/MAINTAINERS.md` owns stable maintainer policy;
- `scripts/project-development-harness.py` owns the executable operator surface;
- `scripts/plan-affected-validation.py` owns static changed-path validation
  selection;
- repository quality, acceptance, packaging, and release scripts own the actual
  product gates they execute;
- Git, pull requests, issues, and release records remain delivery authorities.

The Harness references those authorities. It must not duplicate their content
or become part of the shipped KnoArbor runtime.

## Stable Gate Failure Identity Correction

Gate comparison must identify the semantic failure, not the incidental bytes
printed while reproducing it. Baseline and later phases therefore derive one
bounded, sanitized diagnostic identity from stable failure/error records and
repository-relative diagnostic locations. Timestamps, durations, temporary
paths, ports, run/task IDs, progress output, and ordinary logs cannot change
that identity. A newly failing test, diagnostic code, or repository location
must still produce a different identity and block a hard gate.

The Harness must never retain raw subprocess output merely to compare failures.
Passing gates retain a deterministic passing identity. Existing Initiatives
pinned to an older method remain historical evidence; this correction applies
to the current implementation owner without rewriting old checkpoints.

## Problem

KnoArbor has strong SDD, specialist Skills, deterministic tests, architecture
governance, full-chain acceptance, and release gates. It does not yet have one
executable development system connecting them. The initial Harness records
thirteen stage states, a workspace baseline, role IDs, and gate fingerprints,
but it does not establish:

- typed artifacts and enforceable handoffs between Requirement, Design,
  Implementer, and Reviewer roles;
- human approval and rejection with deterministic rollback;
- a fixed project-owned gate catalog and conditional real-boundary tests;
- fresh project navigation and cross-Initiative status without conversation
  reconstruction;
- idempotent, audited delivery adapters;
- measurements that show where the workflow is slow, flaky, or repeatedly
  rejected.

Consequently the first implementation is an execution kernel, not a complete
development control plane.

## Product Assumptions

1. KnoArbor is currently one repository with Python, renderer, desktop, docs,
   Skills, packaging, and optional live-model boundaries.
2. GitHub is the first supported remote delivery surface. External systems not
   used by this repository are not copied from the reference implementation.
3. Agent cognition remains synchronous and bounded. Deterministic work belongs
   to scripts; persistent multi-Agent teams and Agent-to-Agent messaging are
   not required.
4. Human approval is intentionally retained at authority boundaries. Complete
   does not mean fully autonomous.
5. Existing dirty work may coexist with an Initiative, but only mutations after
   its baseline are attributable to it.

## Goals

1. Admit one Initiative from an objective reference into a frozen route, scope,
   role, artifact, gate, side-effect, and budget contract.
2. Make every stage resumable from versioned repository artifacts without
   reading the originating conversation.
3. Give each cognitive role a minimal, generated work packet with exact readable
   inputs, required outputs, forbidden mutations, and completion evidence.
4. Prevent downstream roles from silently rewriting accepted upstream
   artifacts; changes return through a typed rejection and rollback.
5. Keep human decisions low-frequency, explicit, attributable, and recoverable.
6. Execute only project-owned gates from a fixed catalog and compare baseline A
   with acceptance B.
7. Detect scope overflow including modifications to files already dirty at the
   Initiative baseline.
8. Provide fresh project context from current owners, paths, tests, and active
   Initiative summaries rather than personal memory.
9. Support idempotent delivery planning and a bounded GitHub pull-request
   adapter with explicit side-effect authorization and audit records.
10. Measure stage duration, rejection, retry, gate, scar, scope, Agent-call,
    human-intervention, and delivery outcomes for workflow evolution.
11. Keep credentials, prompts, raw command output, source content, and private
    machine paths out of portable and tracked evidence.
12. Preserve resumability across method upgrades, process crashes, duplicate
    Controllers, remote-write ambiguity, and later unrelated repository work.

## Non-Goals

- Orchestrating product ingest, query, Chat, maintenance, or desktop runtime
  state.
- Replacing feature `tasks.md`, Git commits, pull requests, issues, release
  records, or full-chain acceptance results.
- Automatically deciding product requirements, design acceptance, release
  approval, or destructive external actions.
- Copying TAPD, iWiki, enterprise messaging, multi-repository branch, or Team
  Mode mechanisms that KnoArbor does not currently need.
- Persisting model transcripts, source snippets, raw gate output, credentials,
  or arbitrary shell commands.
- Claiming workflow maturity before real Initiative evidence exists.
- Moving an arbitrary dirty worktree between machines. Cross-machine handoff is
  supported only at a Git-backed checkpoint whose accepted artifact content is
  reachable by exact remote commit.

## Required Assets

The complete system contains six versioned asset classes:

1. **Policy:** short maintainer invariants; mechanically decidable policy moves
   into validation code.
2. **Skills:** on-demand operating procedures for SDD delivery and specialty
   review.
3. **Roles:** Requirement, Design, Implementer, and Reviewer contracts with
   typed inputs, outputs, write boundaries, and prohibitions.
4. **Workflow:** one canonical state machine with stage entry, completion,
   rejection, rollback, circuit-breaker, and human-decision rules.
5. **Gates:** a fixed catalog of hard, soft, and conditional deterministic
   checks mapped to project boundaries.
6. **Adapters:** bounded, idempotent external delivery operations with explicit
   authorization and audit evidence.

## Required Invariants

1. **One control authority.** An Initiative has one immutable manifest, one
   mutable checkpoint containing all current artifact, gate, decision, delivery,
   and stage state, one append-only hash-chained event stream, and one Controller
   writer protected by an Initiative lock. Every other view is regenerated.
   Feature tasks remain in their owning spec.
2. **Fixed workflow vocabulary.** Every run contains initialization,
   requirement analysis, requirement confirmation, current-state evidence,
   design, design confirmation, independent design review, workspace baseline,
   implementation, integration, independent code review, acceptance, and
   closure.
3. **Independent failure boundary.** A stage exists only when it has a distinct
   failure mode or rollback target. Conditional stages remain present and use a
   typed skip decision.
4. **Typed artifacts.** Each stage declares required input and output artifact
   kinds. A `repository_ref` stores a repository-relative path and digest; a
   bounded `control_record` stores normalized verdict or decision fields in the
   checkpoint. Both carry producer attempt, input dependencies, and lifecycle
   state. Source or design bodies are never copied into run state.
5. **Upstream immutability.** Before a downstream stage resolves, every accepted
   upstream artifact digest is revalidated. A mismatch blocks progress.
6. **Role separation.** Requirement cannot author design; Design cannot rewrite
   requirement artifacts; Implementer writes only frozen scope; Reviewer is
   read-only and cannot resolve its own findings by changing implementation.
   Standard and strict runs require distinct Implementer and Reviewer execution
   identities.
7. **Human authority.** Requirement confirmation and strict design confirmation
   require an explicit human decision. Rejection names a permitted rollback
   stage and preserves the rejected attempt in the event stream.
8. **Circuit breaker.** Three consecutive rejections or an exhausted call/retry
   budget moves the Initiative to `awaiting_human`; automatic progress stops.
9. **Frozen workspace.** Baseline records Git identity and repository file
   fingerprints without modifying, cleaning, or staging the worktree.
10. **Fixed gates.** Gate names, severity, command templates, applicable routes,
    and required phases come from the tracked catalog. Initiative input cannot
    introduce arbitrary executable commands.
11. **Failure delta.** Acceptance B is compared to baseline A. New or changed
    hard failures block; identical pre-existing failures remain visible without
    acquiring a new owner.
12. **Soft scars.** Every accepted soft failure has a gate identity, evidence
    fingerprint, owner, acknowledgement, and expiry or removal condition. It is
    visible in review, handoff, delivery, and metrics.
13. **Scope delta.** Any post-baseline changed path outside the manifest allowlist
    blocks acceptance and closure.
14. **Fresh project context.** Context packets derive from current registry,
    ownership map, Git state, allowed paths, accepted artifacts, and local
    Initiative summaries. Conversation history and hidden Memory are not team
    authorities.
15. **Version-addressable method.** A run pins an immutable method version path
    plus digests. A current-version pointer may advance, but a referenced method
    version cannot be removed while an open run uses it.
16. **Crash-consistent mutation.** Every local mutation has a monotonic revision,
    atomic checkpoint replacement, matching event sequence/hash, and startup
    reconciliation. Competing Controllers fail to acquire the single-writer
    lock rather than overwriting state.
17. **Side-effect discipline.** External writes run only in the typed delivery
    substate of `closure`, require manifest authorization, and use a durable
    `intent -> lookup/write -> outcome` protocol with a stable remote identity.
18. **Portable handoff.** A redacted bundle contains control records, method
    identity, hashes, decisions, blockers, metrics, and an exact reachable Git
    OID but no absolute path, secret, raw output, or source content. Import
    revalidates method and artifact reachability before resuming.
19. **Closed immutability.** First closure freezes the acceptance workspace
    snapshot, evidence root hash, and Git identity. Repeated closure validates
    sealed records only; later legitimate repository changes do not invalidate
    historical evidence.
20. **Safe output.** Gate and adapter subprocess output passes through one
    redacting summary proxy. Credential values, private paths, environment
    values, and source bodies cannot enter terminal/session output or records.
21. **Consistent completion.** Registry lifecycle is authoritative. An
    `Implemented` specification cannot retain unchecked required work.

## Route Contract

- `fast`: bounded patch or record-only work. Requirement/design/review stages
  may be skipped with typed rationale. Workspace baseline, implementation,
  focused gates, acceptance, and closure remain mandatory.
- `standard`: requirement analysis and confirmation, design, baseline,
  implementation, integration, independent code review, acceptance, and closure
  are mandatory. Design confirmation and independent design review are
  conditional.
- `strict`: public, persisted, semantic, security, lifecycle, recovery,
  packaging, release, or cross-owner work. Every stage executes; a previously
  captured reproduction may satisfy current-state evidence but cannot remove
  the stage.

## Representative Scenarios

### Normal Standard Change

A GitHub issue or accepted SDD initializes a standard Initiative. Requirement
and Design roles submit typed artifacts; a human confirms the requirement;
baseline gates run; the Implementer submits code and tests; integration gates
pass; an independent Reviewer submits a verdict; acceptance finds no scope or
hard-gate delta; delivery creates or reuses one pull request; closure emits a
portable handoff and metrics.

### Rejected Design

The design review finds an unsupported requirement assumption. It cannot edit
the requirement artifact. It rejects to requirement analysis with a blocker.
Downstream stage resolutions are invalidated, the first attempt remains in the
event stream, and a third consecutive rejection pauses for a human.

### Existing Dirty Work

An unrelated file is dirty before baseline. It remains unchanged during the
Initiative and is not attributed. If its contents later change, scope
verification reports overflow without resetting or overwriting it.

### External Delivery Retry

The GitHub adapter is invoked twice after a network interruption. It looks up a
pull request by repository and head branch, reuses the existing remote object,
and appends an idempotent result instead of creating a duplicate.

### Restart And Handoff

The process stops after design confirmation. A new session validates records,
reads the generated role packet and portable handoff, verifies upstream
digests, and resumes at independent design review without reconstructing chat.

## Acceptance Criteria

1. All six system layers and every file in the immutable method bundle have one
   documented mapping, validate before run creation, and are pinned by new runs.
2. A run can be initialized, resumed, approved, rejected, rolled back,
   baselined, reviewed, accepted, delivered, closed, and inspected without its
   originating conversation.
3. Role packets expose only declared inputs and required outputs; a wrong role,
   missing artifact, changed upstream digest, or Reviewer mutation fails closed.
4. Human approval, rejection, rollback, circuit breaking, and closed
   immutability have deterministic tests.
5. Gate catalog selection, baseline/acceptance delta, conditional gates, scars,
   and raw-output non-persistence have deterministic tests.
6. Scope tests cover new, modified, deleted, directory-prefix, symlink, and
   pre-existing dirty paths.
7. Context and handoff outputs contain current owner evidence and no absolute
   machine paths, source content, raw gate output, or credentials.
8. Delivery adapter tests prove authorization, dry-run behavior, idempotent
   lookup, duplicate prevention, and failure audit without contacting GitHub.
9. Metrics aggregate at least stage duration, rejections, retries, Agent calls,
   human decisions, gates, scars, scope overflow, and delivery state.
10. At least one fast and one strict temporary-repository journey plus crash,
    rejection, gate failure, scope overflow, and delivery-retry cases pass.
11. Crash injection at every local write boundary and a two-Controller race
    prove revision/event consistency and duplicate-write prevention.
12. A method upgrade leaves an older open run resumable, and a later Initiative
    changing the same repository paths does not invalidate a sealed run.
13. Canary credentials and private paths are absent from captured stdout,
    stderr, events, handoff, delivery, gates, metrics, and exception text.
14. The lifecycle remains `Accepted` until five real post-adoption Initiatives
    are reviewed against time, intervention, rejection, quality, and delivery
    evidence.
