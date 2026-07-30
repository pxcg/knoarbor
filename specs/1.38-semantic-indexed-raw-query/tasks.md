# 1.38 Unified Active Raw Evidence Retrieval Tasks

## Lifecycle

Accepted; the lexical baseline is implemented and the cross-source relation
revision remains under verification.

## BM25-Ranked Chat Retrieval Revision

- [x] Restrict query stop terms to conversational scaffolding and retain
  content-bearing domain nouns.
- [x] Delete the post-FTS concept-anchor eligibility predicate.
- [x] Preserve numeric compound-identifier clauses inside the FTS expression.
- [x] Consume the first 12 BM25/RRF-ordered parent candidates per Chat region
  group, deduplicate by vault-scoped Raw identity, retain the first 16
  globally, and expose eligible and retained counts in diagnostics.
- [x] Keep exact-span structural validation after the ranked result window
  without adding confidence, completeness, winner, or source-diversity rules.
- [x] Correct the no-match Gold metric to measure precision among emitted
  no-match outcomes while separately preserving zero false no-match on present
  queries.
- [x] Complete the frozen 42-point before/after retrieval comparison and the
  focused owner/direct-consumer closure.

## Implemented Atom-Only Baseline

- [x] Add field-weighted atom BM25 and claim-centered one-hop expansion.
- [x] Add exact claim evidence resolution and active Raw validation.
- [x] Keep projections and atom prose out of factual answer context.
- [x] Expose the model-free `wiki_query.v2` baseline.

## Phase 1: Root Contracts

- [x] Add vault-scoped RawIdentity, RecallSignal, EvidenceHandle,
  EvidenceCollection, EvidenceRead, QueryPlan, RetrievalSafety, channel status,
  and QueryOutcome.
- [x] Replace vault-wide batch-local claim/relation lookup with revision- and
  source-record-scoped ClaimRef and RelationRef identities.
- [x] Make active evidence resolution one reusable owner for Query, Chat reads,
  citation projection, and context reuse.
- [x] Preserve Query gaps, warnings, stats, and typed failure through every Chat
  adapter.
- [x] Add cancellation checks to snapshot, recall, fusion, paging, and evidence
  reads.

## Phase 2: Snapshot And Recall

- [x] Define atom/edge and Raw-unit lexical documents in one verified retrieval
  generation owned with specification 1.4 persistence and ADR 0008 FTS5.
- [x] Add the shared CJK/technical-identifier analyzer and derived Raw locator
  windows; map every window back to its complete parent SourceUnit.
- [x] Index the source basename on every Raw locator window so named-source
  queries retain source scope without making source-name-only hits eligible;
  mixed queries also require concept coverage in the unit.
- [x] Use one shared deterministic FTS/BM25 query plan before channel rank and
  fusion, with no post-FTS concept-anchor predicate.
- [x] Implement streaming, completely enumerable AtomClaimRecall and
  RawUnitLexicalRecall providers.
- [x] Implement complete ordered channel enumeration, weighted RRF, parent
  identity deduplication, stable continuation cursor, and one resource-based
  RetrievalSafety envelope.
- [x] Eliminate per-query full-corpus reconstruction when an active snapshot is
  available; reconstruct only selected complete units from verified facts.
- [x] Delete every runtime lexical fallback; return typed snapshot status.
- [x] Replace full `RawEvidenceRecord` copies in locator-window metadata with
  the v4 compact locator/rerank contract and active-fact evidence reads.
- [x] Prove automatic v3 replacement, at least 90% Raw-metadata reduction, and
  unchanged deterministic ranking and Gold quality.

## Phase 3: Query V4

- [x] Replace `RawGroundedRetriever` with the unified pipeline.
- [x] Replace `wiki_query.v2` with required `wiki_query.v4` QueryOutcome,
  EvidenceCollection, evidence reads, and trace.
- [x] Update API, CLI, skill, presenter, and Chat consumers in the same contract
  change.
- [x] Delete atom-only runtime, v2 fixtures/readers, bare evidence identities,
  and the Raw-only-unreachable invariant without feature flags.

## Phase 4: Chat Handoff

- [x] Derive `active_corpus_outline.v1` from active source processing and atom
  records.
- [x] Add one derived dominant-language hint per document/chapter without
  exposing source content or changing Ingest.
- [x] Add each active document's complete source-level synthesis to its
  document node as locator-only context without copying it into chapter nodes.
- [x] Resolve selected document/chapter region IDs to source record and source
  unit membership.
- [x] Keep the outline compact: source display metadata, one synthesis per
  document, and top-level chapter labels only.
- [x] Own ordered multi-expression batch execution, deterministic fusion,
  deduplication, and selected active Raw resolution for the linear 1.10 Chat.
- [x] Group literal and model-authored variants by region so they share the
  regional result window.
- [x] Merge alternative variants by each Raw parent's best within-group rank
  rather than additive duplicate voting.
- [x] Attach only images referenced by selected Raw units and emit each image
  once per answer evidence packet.
- [x] Split the BM25/RRF-windowed lightweight `CandidateSet` from answer-facing
  `EvidenceSet`.
- [x] Delete former expression-winner, marginal-anchor, and post-fusion scoring
  gates; select every result-window candidate with exact structural evidence.
- [x] Aggregate repeated claim/window signals at parent-and-channel level and
  hydrate fused parents from Raw locator metadata.
- [x] Preserve complete supporting Raw closure for an accepted relation path;
  ADR 0014 supersedes only the former winner-selected path seed.
- [x] Keep the candidate payload inside Query and hand only `EvidenceSet` to
  linear Chat.
- [x] Replace historical Raw-payload reuse with handle re-resolution through the
  active resolver.
- [x] Ensure retrieved evidence and answer-cited evidence remain separate.
- [x] Preserve and merge every matched span across expressions and channels,
  then expose structure-preserving evidence-packet metrics without changing the
  current answer payload.
- [x] Replace the complete-unit Chat payload with the accepted exact evidence
  segments while retaining local active-unit resolution and attachments.
- [x] Preserve typed candidate/no-match outcomes for the unified Final Answer
  without a Query-owned answer-source route.
- [x] Cache each atom batch and its claim/entity association index once per
  Query execution.

## Phase 5: Verification And Closure

- [x] Add fixed gold retrieval and no-match datasets.
- [x] Measure recall, ranking, identity integrity, complete reachability,
  resource-safety transitions, snapshot rebuild, warm/cold latency, and memory.
- [x] Run the actual focused dependency closure and one isolated real boundary
  evaluation when selected by the release checkpoint.
- [x] Replace stable public Query/Architecture/Contract docs after code and
  tests implement the v3 behavior.
- [x] Remove residual atom-only and compatibility paths, record evidence, and
  return registry lifecycle to `Implemented` only after closure.


## Document And Chapter Scoped Retrieval

- [x] Derive a compact document/top-level-chapter outline from active source
  processing records without changing Ingest.
- [x] Expose only display labels, source type, and opaque region IDs.
- [x] Resolve document and chapter regions to active source record and source
  unit membership.
- [x] Group the unchanged question with one planner-authored expression in each
  selected region and deduplicate results by active Raw identity.
- [x] Remove semantic-community navigation, Query-generated locator queries,
  community bridging, and community-specific cursors from the main path.
- [x] Fall back to one unscoped unchanged query when navigation is empty or
  unavailable.
- [x] Add focused outline, region-filtering, multi-region, unknown-region, and
  fallback tests.

## Derived Snapshot And Batch Cost Closure

- [x] Verify one immutable snapshot per vault for a Query batch and share it
  across all expressions and active Raw reads.
- [x] Normalize repeated parent Raw rerank text into one v6 locator authority.
- [x] Remove duplicate entity, relation, and synthesis evidence excerpts from
  the derived atom locator while preserving exact Claim closure metadata.
- [x] Replace v5 directly through lifecycle-owned rebuild with no compatibility
  reader or query-time migration.
- [x] Replace v6 with v7, removing synthesis rows and graph artifacts.
- [x] Prove exact Raw hydration and focused Query behavior after normalization.
