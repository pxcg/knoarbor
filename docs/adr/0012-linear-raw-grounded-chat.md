# ADR 0012: Linear Raw-Grounded Chat

## Status

Partially Superseded by ADR 0013 and [ADR 0019](0019-unified-final-chat-answer.md)

## Context

KnoArbor is a local-first personal knowledge base. Its default Chat path grew
from a retrieval-and-answer flow into a coverage-driven Agent state machine.
The Chat owner persisted question dimensions, query/evidence attribution,
candidate frontiers, open coverage, cursors, and cross-request retrieval
continuation. It repeatedly alternated complete Raw reads with answer-model
calls and could invoke another semantic planner while coverage remained open.

This mechanism preserved complete candidate reachability, but it conflated
three different guarantees:

1. Query can enumerate every matching active Raw handle.
2. Chat can pass Query evidence to one answer stage without becoming another
   retrieval layer.
3. The answer covers the user's request.

The conflation made ordinary Chat expensive and fragile. A real three-source
comparison retrieved all three sources but read one unit and regenerated at a
time, consumed more than 220,000 tokens, and stopped on the model-call safety
boundary without a complete answer.

## Decision

KnoArbor default Chat uses one linear Raw-grounded pipeline:

```text
request and session validation
  -> model-free Query batch for the literal user question
  -> on trustworthy no_match only: one Query Composer
  -> model-free Query batch for approved semantic expressions
  -> complete active Raw evidence returned by Query
  -> code-owned grounded/general route
  -> one answer semantic stage
  -> citation validation
  -> optional generated image
  -> atomic turn persistence
```

The literal user question is always retrieved first. Candidate evidence goes
straight to grounded synthesis. Only a trustworthy literal-query `no_match`
may invoke Query Composer, which may use dialogue to return a standalone
question and additional natural-language retrieval expressions. It cannot
replace literal scope, select internal identities, declare no-match, or control
evidence lifecycle.

Specification 1.38 remains model-free and owns complete deterministic
enumeration, internal cursors, fusion, active revision resolution, strict typed
outcomes, and complete Raw reads. Chat passes the resulting evidence to the
answer model without a second Chat-owned ranking, filtering, truncation, or
provider-context budget. Any future evidence-volume policy belongs to Query.

Chat invokes exactly one grounded or general answer semantic stage for a
completed turn. The grounded model receives one evidence bundle and returns
ordered answer blocks bound to code-issued support-span IDs plus an optional
explicit gap. It cannot request another retrieval round. General synthesis
remains physically separate and is available only after trustworthy no-match
under ADR 0010.

Chat no longer owns or persists:

- question dimensions or semantic coverage state;
- query-to-dimension or evidence-to-dimension attribution;
- a complete candidate frontier;
- a model retrieval-tool planner;
- iterative read/answer progression;
- Query cursors or cross-request retrieval continuation;
- Raw payloads.

Retry reruns the complete linear turn against current active evidence. Session
v4 preserves messages, identity, final provenance, citations, image artifacts,
compact retrieval trace, usage, lifecycle, and Chat-ingest metadata. One
explicit v3 migration discards superseded control state without dual reads or
dual writes.

Generated images remain presentation artifacts. Source images associated with
selected Raw evidence remain source attachments. Neither can become factual
support without an active Raw support span.

## Model And Code Ownership

The model owns only:

- standalone natural-language question resolution;
- semantic retrieval wording;
- answer composition from the supplied factual bundle;
- selection of supplied support-span IDs;
- optional visual intent when the capability is advertised.

Code owns literal-query preservation, scope, identities, paths, active
revision, retrieval execution, typed outcomes, source
routing, support validation, citation order, safety, cancellation, retry,
persistence, image-provider selection, and artifact storage.

## Failure Semantics

- Every required Query channel must complete and exhaust with zero eligible
  active handle before the batch is `no_match`.
- Explicit local-source questions map trustworthy no-match to
  `knowledge_gap`; ordinary questions may map it to general synthesis.
- Partial usable Raw evidence maps to one grounded answer with an explicit gap.
- Oversized/unusable evidence, integrity failure, unavailable index, timeout,
  cancellation, and resource exhaustion never become no-match or general
  knowledge.
- Query Composer failure after literal no-match preserves that no-match with a
  warning; it does not fabricate a semantic retrieval result.
- Answer failure persists no completed assistant turn.
- Optional image failure preserves the validated text answer and records a
  warning.

## Consequences

- Default Chat has one answer semantic stage and invokes Query Composer only
  after trustworthy literal no-match, excluding gateway retry and optional
  image generation.
- Cross-source comparisons are handled by Query retrieval, not document- or
  wording-specific Chat branches.
- Query evidence ownership remains auditable because Chat does not silently
  discard or reshape the returned evidence set.
- Token use, latency, persisted state, and failure recovery become predictable.
- A future deep-research experience, if justified, must be an explicit product
  mode with a separate accepted contract; it cannot silently re-enter the
  default Chat path.

## Supersession

This ADR partially supersedes ADR 0007's fast/progressive Chat upgrade wording
and ADR 0009's Chat coverage-driven continuation consequences.

ADR 0013 supersedes only this ADR's rule that Query Composer runs after
trustworthy literal no-match. The linear single-batch, single-answer,
Raw-grounded boundary remains accepted.

ADR 0009 remains authoritative for specification 1.38 complete enumeration,
internal cursors, and independent resource-safety outcomes. ADR 0003 remains
authoritative for active Raw factual support. ADR 0010 remains authoritative
for automatic source-separated routing.

## Alternatives Considered

### Preserve The Coverage Loop And Increase Limits

Rejected because it makes the same non-convergent mechanism more expensive.

### Fixed Top-K As Knowledge Absence

Rejected because ranking/context selection cannot prove no-match. Query still
exhausts all required channels before returning that outcome.

### One Huge Prompt Containing Every Match

Rejected because complete recall is not a provider-context requirement and
would amplify privacy exposure, irrelevant material, and cost.

### Hidden Automatic Deep Research

Rejected because ordinary personal knowledge-base Chat needs predictable
latency and behavior.

## Verification

- narrow and follow-up questions use one answer call and exact active Raw
  citations;
- a three-source comparison selects evidence from every matched source and uses
  one answer call;
- strict no-match, partial, integrity, oversized, cancellation, and exhaustion
  routing remain distinct;
- v3 session migration preserves user-visible messages, citations, provenance,
  images, and ingest metadata;
- generated and source-image paths remain presentation-only;
- structural checks find no live dimension-coverage loop, model retrieval
  planner, Chat candidate frontier, or persisted retrieval continuation;
- a real desktop comparison completes without recursive model-call exhaustion.
