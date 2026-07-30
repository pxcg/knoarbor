# ADR 0007: Unified Active Raw Evidence Retrieval

## Status

Partially Superseded by [ADR 0009](0009-complete-retrieval-enumeration.md) for
candidate-count and EvidenceHandle-page limits only.

## Context

ADR 0003 established active Raw source units as local factual authority and
required an explicit claim evidence edge before Raw could be reached. That
keeps model-produced atoms and projections from validating themselves, but it
also makes successful semantic extraction a prerequisite for recall.

The current query therefore cannot find a fact that exists in Raw when ingest
did not extract a matching claim, entity, or relation. Chat cannot distinguish
that extraction miss from a true knowledge no-match. Adding general-model
answers before fixing this boundary would hide local retrieval misses behind
plausible non-grounded prose.

The current implementation also scans complete atom and evidence collections
per query, returns unbounded positive matches, loses typed gap and integrity
details at the Chat adapter, and uses evidence identifiers that are not scoped
by vault. These are one retrieval-contract problem, not independent UI
fallbacks.

## Decision

KnoArbor uses one Unified Active Raw Evidence Retrieval pipeline with multiple
locator channels:

```text
QueryPlan
  -> atom / entity / relation recall -> claim evidence signals
  -> active Raw-unit lexical recall  -> direct Raw locator signals
  -> fuse and deduplicate by vault-scoped Raw identity
  -> active revision and integrity validation
  -> bounded EvidenceHandle page
  -> complete active Raw unit read
```

Both channels are locator mechanisms. Neither is a second factual authority.
All selected material converges on the same identity:

```text
(vault_id, raw_revision_id, source_unit_id, optional_span_identity)
```

Active Raw content remains the only local factual answer material. Claims,
entities, relations, synthesis, projection prose, ranking scores, and prior
assistant answers remain non-factual locators or dialogue state.

Recall channels return typed completion and failure status. `no_match` is valid
only after every required channel completes successfully for the approved query
plan and no eligible unified candidate remains. Index unavailability, active
revision mismatch, evidence integrity failure, invalid scope, cancellation,
and tool failure are never `no_match`.

Candidate generation is bounded before model use. Per-channel scores are not
compared directly; deterministic reciprocal-rank fusion and explicit signals
produce one ordered EvidenceHandle collection. Pagination cursors bind query
fingerprint and retrieval snapshot generation so a later page cannot silently
cross index generations.

Selected Raw units are read completely. Candidate limits and provider-aware
unit packing bound work without character-cutting an accepted unit. A single
unit that cannot fit returns `oversized_evidence`; it is repaired by source
unitization and reingest, not by silent truncation or model summarization.

The query pipeline is model-free. Chat may construct a fast or progressive
QueryPlan, but both call the same retrieval API, evidence identity, active
resolver, and budget contract. Semantic answer coverage belongs to Chat answer
synthesis and code validation, not to lexical score or the query layer.

The development-stage atom-only runtime and `wiki_query.v2` contract are
replaced directly. There is no feature flag, dual reader, score fallback, or
migration adapter. Retrieval snapshots are rebuilt from active facts, and old
development fixtures are replaced.

## Consequences

- Raw facts remain available even when semantic extraction missed a locator.
- Claims remain valuable semantic and provenance signals without monopolizing
  access to Raw.
- Query and Chat share one evidence identity and one active resolver.
- A trustworthy no-match can safely participate in source-separated Chat
  routing after calibration.
- Candidate and context growth become explicit and measurable.
- The local index now includes Raw-unit lexical documents, increasing rebuild
  time and derived index size while leaving factual storage unchanged.
- ADR 0003 continues to own Raw factual authority but no longer owns the sole
  locator route.

## Alternatives Considered

### Preserve Atom-Only Recall

Rejected because extraction misses are indistinguishable from knowledge
absence and would incorrectly trigger general-model answers.

### Independent Raw Search Fallback

Rejected because a fallback would create a second untyped ranking path. Raw
lexical recall is a first-class channel inside the same pipeline and converges
before evidence selection.

### Add Dense Retrieval Immediately

Deferred until a fixed evaluation set shows lexical hybrid recall is
insufficient. Dense retrieval must implement the same RecallSignal and
EvidenceHandle contracts if later added.

### Compare Atom And Raw BM25 Scores Directly

Rejected because the corpora, document lengths, and score distributions are
not comparable. Fusion uses ranks and explicit deterministic signals.

### Run A Full Agentic Pipeline For Every Query

Rejected because simple factual questions do not require model planning.
Progressive planning is an escalation within one retrieval session.

## Verification

- Gold cases cover direct claim, alias, relation, Raw-only extraction miss,
  synonym/CJK queries, multi-dimensional questions, true out-of-scope queries,
  inactive revisions, corrupt edges, duplicate units, and oversized evidence.
- Active Raw identity and citation integrity are exact for every returned unit.
- Raw-only cases are recovered without regressing claim-backed cases.
- `no_match` precision reaches the accepted gate before general fallback is
  enabled.
- Candidate budgets, stable cursors, snapshot generation, rebuildability, and
  warm/cold latency are measured on a representative local corpus.
- Fast and progressive Chat paths call the same query and evidence-read owners.

## Follow-Up

- Specification 1.38 owns retrieval contracts and implementation.
- Specification 1.10 owns fast/progressive Chat planning, coverage, answer
  routing, session lifecycle, and cancellation.
- Specification 1.18 owns grounded and general synthesizer prompt contracts.
- [ADR 0009](0009-complete-retrieval-enumeration.md) replaces fixed result-count
  limits with complete enumeration plus independent resource safety.
