# 1.38 Unified Active Raw Evidence Retrieval Requirements

## Lifecycle

Accepted. The unified active Raw lexical baseline is implemented; the accepted
cross-source relation retrieval revision remains under implementation.

## Ownership

This specification owns model-free local recall, locator-signal fusion,
vault-scoped evidence handles, bounded cross-source relation traversal, active
Raw resolution, BM25 result windows, structural evidence selection,
structure-preserving evidence segments, typed query outcomes, and the
locator-only document/chapter outline consumed by Chat navigation.

Neighboring owners remain:

- `1.26` owns model extraction and source-grounded atom production;
- `1.27` owns deterministic entity identity and aliases;
- `1.4` owns persisted machine-index generations and rebuild mechanics;
- `1.10` owns linear Chat orchestration, the optional Retrieval Planner,
  region selection, answer routing, sessions, stream, retry, and
  ingest handoff;
- `1.18` owns grounded and general answer prompts;
- ADR 0003 owns active Raw factual authority;
- ADR 0007 owns unified multi-channel Raw location.
- ADR 0008 owns the single immutable SQLite FTS5 snapshot decision.
- ADR 0009 owns complete result reachability and independent resource safety.
- ADR 0011 owns the two-relation-edge Graph-assisted retrieval boundary.
- ADR 0014 owns document/chapter-scoped retrieval.

This specification continues to supersede the page-first evidence selection in
`1.12`. Projection pages remain reading and navigation artifacts.

## BM25 Query And Gold Integrity Correction

1. Query scaffolding may be removed before search, but domain nouns such as
   architecture, framework, component, technology, method, setting, location,
   topic, and effect remain ordinary BM25 terms.
2. FTS match plus field-weighted BM25 order owns lexical eligibility. A second
   hand-authored concept-anchor predicate MUST NOT veto or force-admit a row.
3. Compound technical identifiers retain their complete and constituent forms
   in the FTS expression; they are ranking/query terms rather than a separate
   semantic-confidence system.
4. Document and top-level chapter regions provide only candidate scope. The
   unchanged question remains one expression in every selected region group.
5. A chapter region includes every lower-level source unit under that chapter.
6. A navigation scope cannot seed or force-admit Raw.
7. Retrieval quality fixtures must use semantically opaque source paths and
   identities. Expected query anchors may occur only in the intended indexed
   content, aliases, entities, or claims—not in fixture plumbing.
8. Merged-channel quality must be evaluated on a genuinely complementary
   corpus. It must retain perfect expected-source recall/ranking and outperform
   each isolated channel without weakening thresholds when one channel appears
   perfect because of fixture leakage.

## Product Assumptions

KnoArbor is a local-first personal knowledge system. Retrieval must remain
inspectable and deterministic before answer generation, but mature knowledge
recall cannot depend on perfect model extraction during ingest. Derived indexes
may optimize access but are always rebuildable from active facts.

## Goals

1. Recall active Raw facts through both semantic atom/claim signals and direct
   Raw-unit lexical signals.
2. Converge every channel on one vault-scoped active Raw identity and resolver.
3. Preserve claims as high-value semantic and provenance signals without making
   them the only path to Raw.
4. Produce trustworthy typed no-match, failure, stale, and integrity outcomes.
5. Keep the complete ordered provider stream reachable to single-query callers,
   while Chat batch retrieval consumes documented regional and global BM25/RRF
   result windows before Raw reads.
6. Give `/query` and Chat the same retrieval contracts and factual material.
7. Keep vector recall and model reranking optional future providers rather than
   prerequisites for the lexical hybrid baseline.
8. Retrieve evidence-connected one- and two-edge relations across source
   revisions without changing active Raw factual authority.
9. Keep semantic relevance in BM25 and reciprocal-rank ordering. After the
   ranked result window, structural selection admits every unique candidate
   backed by an exact Claim or Raw locator span without another semantic score.

## Non-Goals

- Page-body or renderer navigation-graph ranking as a factual retrieval channel.
- Projection prose, claim prose, synthesis, ranking signals, or assistant text
  as factual answer material.
- A separate Raw-search fallback beside the main query pipeline.
- Model-based query planning inside `/query`.
- Dense/vector recall or cross-encoder reranking before lexical evaluation
  demonstrates a need.
- Arbitrary character truncation, model summaries, or locator prose as
  substitutes for exact structure-preserving Raw evidence segments.
- General-model answers, Web Search, Chat persistence, or UI source policy.
- Compatibility readers, dual indexes, or feature flags for the atom-only
  development runtime.
- A caller-selected GraphRAG mode or generated community prose as
  factual evidence, or a recursive default research loop.

## Requirements

### Document And Chapter Navigation

1. Query derives `active_corpus_outline.v1` from current active source
   processing and atom records without changing Ingest.
2. The visible outline contains vault labels, document display names and types,
   each document's complete source-level synthesis, top-level chapter labels,
   derived dominant-language hints, and opaque `region_id` values. The
   synthesis remains locator-only and is never factual answer material. The
   outline excludes Raw, individual claim/entity/relation rows, attachment,
   storage path, and revision/evidence content.
3. Every document has a document region containing all of its active source
   units. Every recognized top-level chapter has a chapter region containing
   its lower-level source units.
4. Region resolution is deterministic. Unknown regions are rejected before
   retrieval.
5. Query batch accepts ordered expressions with an optional `region_id` and
   region `group_id`. Chat supplies the unchanged question and at most one
   model-authored regional expression in each selected group.
   Region filtering uses both active source record and source unit identity
   before fusion and structural selection.
6. Each selected region shares one 12-parent result window across all of its
   expressions. Expressions in one group are alternative formulations, so one
   parent contributes only its best within-group rank rather than a sum of
   duplicate votes. Several groups run in one Query-owned batch, deduplicate by
   vault-scoped active Raw identity, and share one 16-parent global window.
7. Empty or unavailable navigation uses one unscoped unchanged query.
8. Region membership is neither evidence nor a relevance signal and cannot
   select Raw by itself.

### Batch Query Handoff For Chat

The model-free Query owner MUST accept an ordered batch for one Chat answer
obligation. It MUST:

- preserve all expressions and their region-group identity;
- execute every expression through the same active atom/claim, Raw lexical,
  relation, integrity, and structural-evidence contracts used by single-query
  retrieval;
- apply a selected region only as a candidate-scope constraint for its own
  expression;
- fuse and deduplicate matches by vault-scoped active Raw identity;
- fuse variants within the documented result window for each region group,
  deduplicate them by vault-scoped active
  Raw identity, and apply the documented global result window;
- select the answer-facing `EvidenceSet` from every globally retained candidate
  with an exact Claim or Raw locator span, never by a second semantic score,
  confidence threshold, or region membership;
- re-resolve selected handles against the active revision before returning Raw;
- return exact structure-preserving Raw segments and retained source
  attachments actually referenced by those Raw units to Chat.

A completed batch with no structurally selected evidence is `no_match` only
when every
required channel completed successfully. Runtime safety exhaustion and index
failure remain separately typed. Chat MUST NOT rerank, filter, truncate, or
read candidates lacking exact evidence spans.

### R1. One Factual Authority, Multiple Locator Channels

Atom/claim, Raw-unit lexical, and accepted relation-path recall MAY independently
produce locator signals. They MUST converge before selection, and only active
Raw content may be returned as local factual evidence.

### R2. Vault-Scoped Raw Identity

Every candidate and evidence handle MUST identify at least `vault_id`,
`raw_revision_id`, and `source_unit_id`. Span-specific handles additionally
identify the claim/span. Bare evidence IDs that can collide across vaults are
invalid.

Claim and relation identities MUST also include their factual revision and
source-record batch namespace. Batch-local IDs such as `C1` or `R1` MUST never
be resolved through a vault-wide dictionary. Relation `source_claim_ids`
resolve only inside the relation's own batch namespace.

### R3. Atom And Claim Recall

Direct claim matches, entity aliases, and relation `source_claim_ids` remain
semantic locator signals. Claim evidence edges contribute provenance and
ranking signals. Resolving atom matches to claims MUST read and validate each
active `(revision_id, source_record_id)` batch at most once per Query execution
and reuse a batch-local claim/entity association index. Synthesis remains
navigation-only.

### R4. Raw-Unit Lexical Recall

Active Raw units MUST be searchable through bounded overlapping locator windows
even when no matching atom exists. A window match does not invent a claim or
claim citation; it maps to and deduplicates by the same parent active unit
identity used by claim-backed candidates. Windows rank and highlight only;
selected evidence always retains the parent SourceUnit identity and exact
source offsets. Every Raw locator
window also carries its source basename as a low-weight BM25 field so a
named-source query can scope relevant sibling units that do not repeat the
document name in their body. Source-name, title, structure, and content matches
contribute through their configured field weights. Partial content support
remains rankable; Query does not require one Raw unit to satisfy every answer
facet through a separate Boolean predicate.

### R5. Deterministic Fusion

Each channel returns a deterministically ordered signal stream. Fusion MUST
deduplicate by Raw identity, use rank-based and explicit deterministic signals,
and MUST NOT compare unrelated BM25 scores as if they shared one scale.
Repeated claims or locator windows for one parent Raw unit remain traceable but
MUST NOT increase its rank merely through signal count; each channel contributes
its best parent-level rank, with only bounded cross-channel corroboration. Raw
locator metadata MUST hydrate the fused parent even when an atom/claim signal
created that parent first. Single-query provider streams remain exhaustively
reachable; the Chat batch result window is applied after each expression's
BM25/RRF order and is reported in diagnostics.

### R6. Complete Enumeration And Safety

An approved QueryPlan enumerates all matching atom/claim and Raw locator
signals, folds them to parent Raw identities, and exhausts the ordered result
set unless cancelled or stopped by a typed resource safety limit. Internal
batches and cursors are transport details, not semantic top-k limits. Stable
cursors bind query fingerprint, vault scope, and retrieval snapshot generation
and MUST NOT cross generations silently.

The one typed `RetrievalSafety` contract limits wall time, accumulated bytes,
memory, provider-context tokens, and model/tool calls. It is independent from
the Chat result window and MUST NOT silently convert an incomplete provider
stream into no-match. Structural selection MUST NOT add another score,
confidence estimate, or completeness judgment after the result window. Safety exhaustion returns
`resource_exhausted` with continuation state and can never mean no-match.

### R7. Active Resolution And Integrity

Every evidence read revalidates active revision, processing record, unit
identity, and available span/hash metadata. Historical session payloads cannot
bypass this resolver. Stale and corrupt handles return typed outcomes and no
Raw content.

### R8. Structure-Preserving Evidence Reads

Once a unit is selected, Query MUST merge every matched span contributed by
all expressions and recall channels, re-resolve the active parent SourceUnit,
and project exact Raw segments with original offsets. Each segment expands to
the smallest complete local structure that preserves meaning: sentence or
paragraph for prose, complete table/list/code/formula block when intersected.
Disjoint relevant structures remain separate segments under one Raw identity.
Query MUST NOT apply arbitrary character cuts, discard a matched span, or
substitute a summary. The complete active unit remains available to the
resolver and human source view but does not cross the answer-model boundary by
default.

### R9. Typed Channel And Query Outcomes

The query result records channel completion, query variants searched,
candidate counts, exclusions, warnings, snapshot generation, and one result
status such as `candidates`, `no_match`, `integrity_error`,
`index_unavailable`, `invalid_query`, `invalid_scope`, `resource_exhausted`, or
`cancelled`.

### R10. Strict No-Match

`no_match` is valid only when every required recall channel completes
successfully for the approved QueryPlan, its result stream is exhausted, and no
eligible active Raw handle remains. Low score, extraction miss, partial pages,
index absence, active-revision failure, cancellation, or tool error MUST NOT be
represented as no-match. Chat additionally owns unresolved-reference and
planning-exhaustion checks before promoting a plan result to a turn-level
no-match.

### R11. Model-Free Query Contract

`/query` remains model-free and moves directly to `wiki_query.v4`. The response
exposes typed outcome, the ordered lightweight `CandidateSet`, the structurally
selected `EvidenceSet` with exact Raw evidence, channel trace, gaps,
warnings, and optional projection navigation without v2 compatibility fields.

### R12. Chat Handoff

Linear Chat uses the same search, enumeration, structural evidence selection,
evidence read, and active resolver. Query does not declare natural-language
answer sufficiency; the answer stage receives only `EvidenceSet`.

### R13. Explainable Trace

Trace identifies channel, matched terms, atom/claim signals, Raw locator spans,
fusion contributions, exclusions, active validation, and evidence identity.
Retrieved evidence and answer-cited evidence remain distinct.

### R14. Rebuildable Snapshot

Atom and Raw lexical documents are stored in the one verified SQLite FTS5
retrieval generation defined by ADR 0008 and derived from active facts. Index
absence triggers a lifecycle-owned deterministic rebuild request or typed
unavailable result, never an inline read-time rebuild or changed semantics.

Raw locator rows MUST persist only the parent identity, locator spans,
presentation metadata needed to construct a handle, and compact normalized text
needed by BM25 ranking. They MUST NOT duplicate a
serialized `RawEvidenceRecord`, atom-ID collections, source-unit metadata, or
answer-bearing factual payload fields. The locator ranking text is derived
input, never evidence returned to Query or Chat. Every selected unit MUST be
loaded from its verified active factual revision and validated against the
handle before it becomes an `EvidenceRead`.

An unsupported retrieval schema is replaced by the existing lifecycle owner
through a clean rebuild and atomic publication. Query readers do not retain a
compatibility reader or migrate factual data.

### R15. Deterministic Query Normalization

Normalization MUST be model-free and identical at index and query time. It
includes Unicode NFKC, case folding, full-width normalization, canonical entity
aliases, deterministic camel/snake/kebab identifier variants, Chinese bigrams
for recall, Chinese trigrams for precision, and full phrases as BM25 terms.
Only conversational question scaffolding is removed; content-bearing nouns
remain searchable. N-grams MUST NOT become a second semantic eligibility
system.

### R16. Learning-Free Baseline

The accepted lexical baseline uses fielded BM25 and weighted reciprocal-rank
fusion. It includes no dense retrieval, embedding
model, vector database, cross-encoder, LLM reranker, default pseudo-relevance
feedback, learned weights, or runtime scorer fallback. Relation atoms remain ordinary lexical locators and close through their batch-local `source_claim_ids`; no graph traversal or graph-specific rank is part of Query.

### R17. Structural Evidence Selection

FTS match and field-weighted BM25 own lexical eligibility and order; compound
identifier clauses remain part of the FTS expression. Fusion unions provider
signals and deduplicates by active Raw identity. Chat batch retrieval takes the
documented leading result window per region group, deduplicates the retained
parents, and then takes the documented leading global result window. The
post-window structural boundary MUST NOT re-estimate semantic relevance,
coverage, confidence, or answer completeness.

Every unique candidate inside both result windows with at least one valid exact
Claim evidence span or Raw locator span enters
`EvidenceSet`. Candidates without an exact span remain traceable but cannot cross the answer boundary.
The decision records only query IDs, contributing channels, and span count.
BM25 and reciprocal-rank order determine the result windows. None of these ranks asserts factual confidence or
answer completeness.

If every required channel completes and no exact evidence span exists, the
result is `no_match`. Index failure, cancellation, or safety exhaustion cannot
produce no-match.

## Representative Scenarios

1. A direct claim matches and resolves through its evidence edge.
2. An entity alias or relation locates a claim-backed Raw unit.
3. Raw contains the answer but extraction produced no matching atom; Raw lexical
   recall still returns the active unit.
4. Claim and Raw channels find the same unit; fusion returns one handle with
   both signals.
5. Two vaults contain colliding local IDs; vault-scoped handles remain distinct.
6. A stored handle points to a superseded revision; evidence read returns stale
   and requires new search.
7. One channel fails while another returns nothing; the result is failure, not
   no-match.
8. A cursor is reused after index generation changes; the request is rejected
   rather than mixing snapshots.
9. A selected unit exceeds the model budget; query returns oversized evidence
   without truncation.
10. A question sharing only a generic word may produce a low-ranked lexical
    candidate; answer routing must not reinterpret BM25 rank as factual support.
11. A long or comparative question keeps partial evidence reachable when a
    source strongly covers any one original-query anchor.

## Acceptance Criteria

- Raw-only gold cases are retrieved while active Raw remains the sole factual
  payload.
- Claim-backed baseline recall does not regress materially.
- Every public evidence handle is vault-scoped and active-resolved.
- `no_match` precision reaches at least 95% on the accepted gold set before
  Chat general fallback is enabled.
- Active identity and citation-span integrity reach 100% in deterministic tests.
- Resource safety behavior, stable cursors, rebuilds, and warm/cold
  latency meet the verification plan.
- Compact Raw locator metadata reduces repeated retrieval-snapshot bytes by at
  least 90% on the accepted six-document desktop corpus while preserving
  complete selected-unit content, handle identity, ranking, and Gold metrics.
- Atom-only runtime, `wiki_query.v2`, and tests asserting Raw-only
  unreachability are deleted without a compatibility path.
- A multi-expression Query batch verifies one immutable snapshot per selected
  vault and reuses it for expression retrieval and active Raw resolution.
- The v7 derived snapshot stores parent Raw rerank text once per evidence
  identity and omits duplicate entity/relation/synthesis evidence excerpts.
  Exact Claim spans, complete active Raw reads, ranking, graph closure, and
  public evidence identity remain unchanged.
- An unsupported v6 snapshot is rebuilt through the existing lifecycle owner;
  no v6 reader, dual schema, or query-time migration remains.
