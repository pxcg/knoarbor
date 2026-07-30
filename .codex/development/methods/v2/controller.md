# KnoArbor Development Method v2 Controller

## Admission

Validate the complete pinned method bundle, freeze route, scope, roles, gates,
budgets, and authorized side effects, then create revision zero. Never infer a
missing contract from conversation history.

## Relay

For the current stage, generate the owning role packet, verify accepted inputs,
start one synchronous execution, accept only declared output kinds, and resolve
the stage through one checkpoint transaction. Human stages use explicit approve
or reject decisions. Rejection follows the workflow rollback graph and
invalidates the downstream artifact dependency closure.

## Deterministic Boundaries

Capture workspace and gate baseline before implementation. Run catalogued gates
at their declared phase. Before Reviewer completion, acceptance, delivery, and
closure, verify upstream artifact digests, repository scope, and required gate
state. Do not forward raw subprocess output.

## Delivery And Closure

Delivery is a closure substate. Record an intent before any remote lookup or
write. On ambiguous retry, repeat lookup by the frozen idempotency identity.
Never commit, push, mutate an issue, notify, or release without a separately
declared and authorized adapter. Seal the snapshot when acceptance is approved;
later validation checks that historical seal rather than the evolved worktree.
