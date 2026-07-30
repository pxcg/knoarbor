# ADR 0015: BM25-Ranked Chat Retrieval

## Status

Partially Superseded by [ADR 0016](0016-direction-first-retrieval-planning.md)

## Context

The lexical snapshot already calculates field-weighted BM25, but a later
hand-authored concept-anchor predicate independently rejected rows. That
predicate was simultaneously too strict for mixed-language and conversational
questions and too permissive when a source acronym appeared throughout a long
document. Removing post-fusion scoring then exposed the other half of the
problem: every structurally valid lexical candidate crossed into Raw reads, so
BM25 order had no practical answer-boundary effect.

Question scaffolding had also grown into a mixed stop list that removed
content-bearing nouns such as technology, method, setting, location, topic, and
effect while retaining pronoun scaffolding such as “这是”.

## Decision

Query uses one learning-free ranked lexical path:

```text
unchanged question
  -> remove conversational scaffolding only
  -> FTS5 OR recall with CJK phrases/bigrams/trigrams and identifier variants
  -> field-weighted BM25 per Claim and Raw channel
  -> parent-Raw deduplication and weighted reciprocal-rank fusion
  -> leading 12-parent result window per Chat expression
  -> cross-expression Raw deduplication and leading 16-parent global window
  -> exact-span structural validation
  -> active Raw reads
```

Domain nouns remain searchable. Compound identifiers containing numeric parts
must retain those numeric identity clauses in FTS; this prevents a generic
surrounding word from substituting for an explicitly named version or ID.
There is no separate concept-coverage, confidence, source-diversity, winner, or
semantic-admission rule after BM25.

Single-query provider streams remain exhaustively reachable with existing
continuation and resource-safety semantics. The 12-parent regional and
16-parent global windows belong only to the Query-owned Chat batch handoff.
Each selected document or chapter region receives its own regional window,
then the combined set is deduplicated and globally windowed before Raw reads.
The windows are retrieval result contracts, not context-character budgets,
user settings, or claims that later candidates are factually irrelevant.

`no_match` continues to mean that the required lexical streams produced no
candidate. Weak lexical overlap may conservatively remain on the local path.
The general-routing gate measures precision among emitted no-match outcomes and
false no-match on knowledge-present queries; it does not require every absent
question to emit no-match.

## Consequences

- BM25 and reciprocal-rank order now determine which Chat candidates are read.
- Mixed-language questions still require lexical overlap after navigation;
  Query does not translate or invent a semantic rewrite.
- Weak overlaps can consume a result-window slot, but no custom Boolean rule
  can erase a stronger BM25 result.
- Chat evidence volume is bounded globally rather than growing linearly with
  selected regions or every match in a long source.
- General knowledge may remain on the local gap path when weak overlap exists;
  this is conservative and cannot create a false general answer.

## Supersession

This ADR supersedes ADR 0009 only for the answer-facing Chat batch result
window. ADR 0009 remains authoritative for complete single-query provider
enumeration, continuation, and independent resource safety. It supersedes the
concept-anchor eligibility portions of specification 1.38; ADR 0014 remains
authoritative for unchanged-question document/chapter navigation.

## Alternatives

### Restore A Semantic Confidence Threshold

Rejected because score calibration became a second relevance authority and
repeatedly removed valid evidence.

### Send Every BM25 Match To Chat

Rejected because ranking would not affect the answer boundary and long
documents would recreate unbounded Raw evidence packets.

### Remove All Stop Terms

Rejected because pure conversational scaffolding adds no useful lexical signal.

### Add An LLM Reranker

Rejected because token and latency cost would grow with candidate count and
make model-free Query behavior provider-dependent.

## Verification

- architecture, framework, component, technology, method, setting, location,
  topic, and effect remain query terms;
- conversational scaffolding does not become a query term;
- BM25 order is preserved through each 12-parent regional result window;
- more than 12 eligible parents are reported per expression, while no more than
  16 deduplicated parents cross the global Chat batch CandidateSet boundary;
- all windowed candidates with exact spans cross structural validation;
- fixed present/no-match Gold proves zero false no-match on present queries and
  at least 95% lower-confidence-bound precision among emitted no-match results;
- the frozen 42-point retrieval suite records expected-document reachability,
  Raw-anchor reachability, candidate count, evidence characters, and latency.

