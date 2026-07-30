# ADR 0009: Complete Retrieval Enumeration With Resource Safety

## Status

Partially Superseded

ADR 0015 supersedes complete enumeration only at the answer-facing Chat batch
handoff by adding one BM25/RRF result window per expression. Complete
single-query provider enumeration, continuation, and resource safety remain
accepted here.

## Context

ADR 0007 introduced bounded candidate pages to control retrieval work. KnoArbor
ingest deliberately produces many fine-grained claims and Raw locator windows.
A fixed top-k, page count, or evidence-unit count can therefore discard a
relevant parent SourceUnit before claim/window signals are folded and before
Chat evaluates semantic coverage.

The product still needs protection from runaway execution, large sources,
provider context limits, and repeated Agent planning. Result-count truncation
and resource safety are different concerns and must not share one budget.

## Decision

Every approved lexical QueryPlan exposes a complete deterministic ordered match
stream. The retrieval owner consumes internal SQLite batches automatically,
maps all claim/window signals to parent active Raw identities, deduplicates and
ranks them, and keeps every matching parent candidate reachable until the
stream is exhausted.

There is no semantic top-k, transport-page count, candidate count, parent-unit
count, or evidence-read count. Internal batching and cursors bound memory and
transport only; changing their size cannot change the complete result set.

One typed resource-safety envelope independently limits:

- wall-clock time and cancellation;
- accumulated bytes and process memory;
- provider-context tokens;
- model and tool calls.

A safety stop returns `resource_exhausted`, the already validated grounded
coverage, and continuation state. It never returns no-match and never enables a
general-model answer. No-match requires successful exhaustion of every required
channel and zero eligible active Raw candidates.

Chat stops normally on validated semantic coverage, exhausted result streams,
or deterministic lack of information gain. It stops abnormally on explicit
resource safety and reports that state. Neither path silently discards a
matching candidate because of its ordinal rank.

This decision supersedes only ADR 0007's bounded EvidenceHandle-page and
candidate-limit semantics. ADR 0007 remains authoritative for unified channels,
Raw identity, active resolution, fusion, typed failures, and strict no-match.

## Consequences

- Fine-grained claims cannot crowd relevant parent Raw units out through an
  arbitrary early top-k.
- Retrieval may enumerate more lightweight locator rows, so streaming,
  parent-level deduplication, bounded memory, cancellation, and observability
  are required.
- The answer model still receives provider-safe evidence packages; provider
  context size is a resource boundary, not a claim that remaining evidence does
  not exist.
- A safety stop is resumable and auditable rather than being misreported as
  knowledge absence.

## Alternatives Considered

### Increase The Fixed Top-K

Rejected because any fixed number preserves the same correctness failure at a
larger corpus size.

### Limit Claims Before Parent-Unit Folding

Rejected because fine-grained claims from one source can crowd out distinct
sources before evidence identity is known.

### Remove All Safety Limits

Rejected because local queries and Agent loops still require cancellation,
memory, provider-context, and execution-time protection.

## Verification

- a relevant candidate below former top-k boundaries remains reachable;
- changing internal SQLite batch size does not change the ranked parent result
  set;
- duplicate fine-grained claims/windows fold to one parent identity without
  hiding other matching parents;
- every required channel can prove exhaustion before no-match;
- each resource-safety trigger returns `resource_exhausted`, continuation state,
  and no general-answer transition;
- memory remains bounded while result reachability remains complete.

## Follow-Up

- Specification 1.38 owns complete lexical enumeration, parent folding,
  continuation, and Query safety outcomes.
- Specification 1.10 owns coverage-driven Agent continuation and the Chat
  projection of resource exhaustion.

