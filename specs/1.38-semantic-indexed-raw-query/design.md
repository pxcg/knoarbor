# 1.38 Unified Active Raw Evidence Retrieval Design

## Lifecycle And Decision

Accepted. The implemented lexical baseline replaces the former atom-only
runtime with one model-free retrieval pipeline. The accepted cross-source
relation revision remains under verification before full closure.

```text
QueryPlan
  -> RetrievalSnapshot
  -> parallel RecallProviders
       -> AtomClaimRecall
       -> RawUnitLexicalRecall
  -> RecallFusion
  -> CandidateSet
  -> StructuralEvidenceSelection
  -> EvidenceSet
  -> ActiveEvidenceResolver
  -> complete EvidenceRead
  -> StructurePreservingSegmentProjection
  -> wiki_query.v4 / Chat handoff
```

Before Chat constructs this model-free batch, Query exposes a deterministic
`active_corpus_outline.v1` locator view from active source processing and atom
records:

```text
active source processing + atom records
  -> document regions
     -> complete document-level synthesis locator
  -> top-level chapter regions containing their lower-level source units
  -> locator-only document/chapter outline
```

The outline exposes document and top-level chapter labels, each document's
complete source-level synthesis, dominant language hints, and opaque region
IDs. Synthesis is document-level locator metadata: it helps the planner select
a document when headings do not match the user's wording, but cannot seed or
authorize Raw and never becomes factual answer material. The outline excludes
Raw, individual Claim/Entity/Relation rows, attachments, revision/evidence
identities, and other projection content. Chat may present it to one Retrieval
Planner. Query executes the literal and regional expressions in one group per selected region,
filters lightweight candidates by active source record and source unit
membership, and then uses ordinary fusion and structural selection. Membership
is not evidence. Empty planning executes one unscoped unchanged
question.

There is one query implementation, not an atom path plus a Raw fallback.

## BM25 Query Eligibility

`LexicalQueryPlan` owns only deterministic normalization and FTS expression
construction. It removes conversational scaffolding, preserves
content-bearing nouns, emits CJK phrase/bigram/trigram terms and Latin
identifier variants, and gives compound technical identifiers one structured
FTS clause. It does not evaluate a second concept-coverage or semantic
eligibility predicate over returned rows.

FTS5 owns lexical matching. Field-weighted BM25 owns order within each Claim and
Raw stream. Source identity remains a low-weight field rather than a Boolean
authorization rule. Cross-language meaning is not invented by Query; Chat may
supply a planner-authored regional expression, while each expression still
needs indexed lexical overlap to rank the correct unit.

Gold fixtures separate semantic content from fixture addressing. Generated
source-record IDs and raw/source paths use opaque stable tokens derived from the
fixture identity so no addressing field can satisfy a query. Expected-source
assertions resolve through that same deterministic fixture-identity function.
Channel-complementarity assertions are then calculated from genuine atom-only,
Raw-only, and dual-channel evidence.

## Sources Of Truth

| Meaning | Authority | Derived use |
| --- | --- | --- |
| Active factual content | active `SourceUnitRecord` selected by source head | Raw lexical document and answer evidence |
| Semantic locator | active knowledge atom batch | atom/claim recall signal |
| Claim-to-Raw provenance | claim evidence edge | recall signal and audit trace |
| Active Raw identity | `(vault_id, raw_revision_id, source_unit_id)` | fusion and evidence handle |
| Claim identity | `(revision_id, source_record_id, local_claim_id)` | batch-safe claim and relation resolution |
| Retrieval snapshot | verified SQLite FTS5 generation derived from active facts | local search acceleration |
| Projection page | deterministic projection | optional human navigation |
| Query expressions | unchanged user question plus optional code-validated region | locator input; never factual authority |
| Retrieval breadth | Query signals observed in the current corpus | adaptive; never selected by Chat |

## Typed Stage Contracts

```text
QueryPlan {
  original_query
  query_variants
  source_scope
  cursor
  safety: RetrievalSafety
}

RecallSignal {
  channel: atom_claim | raw_lexical
  raw_identity
  channel_rank
  channel_score
  matched_terms
  claim_ids
  matched_spans
}

EvidenceHandle {
  evidence_id
  raw_identity
  retrieval_generation_id
  active_fact_generation
  source_metadata
  signals[]
  fused_rank
  content_chars
}

EvidenceCollection {
  handles[]
  exhausted
  continuation_cursor
  query_fingerprint
  snapshot_generation
  channel_statuses[]
}

CandidateSet {
  ordered_handles[]
  per_expression_matches
  structural_decisions_by_handle
}

EvidenceSet {
  selected_handles[]
  query_ids_by_handle
  selection_reasons_by_handle
}

EvidenceRead {
  handle
  complete_active_unit
  validation
}

EvidenceSegment {
  text
  char_start
  char_end
}

QueryOutcome {
  status
  searched_queries[]
  completed_channels[]
  evidence_ids[]
  gaps[]
  warnings[]
}
```

These are immutable stage outputs. No shared mutable Chat-style context crosses
the query stages.

## Query Plan

`/query` constructs a model-free plan from the original query, explicit caller
scope, cursor, and resource safety envelope. Chat may provide approved query variants and source
scope from its fast or progressive plan. Query validates and executes those
values but does not call a model or infer conversational intent.

The query fingerprint includes normalized original query, variants, and scope.
Cursor validation binds that fingerprint to a retrieval generation; resource
safety settings do not change candidate identity or order.

## Retrieval Snapshot

The snapshot contains:

- field-weighted Claim, Entity, and Relation atom documents;
- active Raw-unit lexical documents;
- compact active source-unit identity, locator spans, handle presentation
  fields, and complete parent-unit rerank text;
- generation manifest and content hashes.

Specification 1.4 and ADR 0008 own the composite generation, SQLite FTS5
storage, verification, capability probe, and `CURRENT` selection. Specification
1.38 owns document meaning, tokenization, channel behavior, fusion, and query
semantics. An in-memory cache may hold verified rows from the selected
generation but never becomes authority.

The public dependency is `LexicalSnapshot`, not SQLite APIs. There is one FTS5
implementation and no per-request BM25 or custom-postings fallback. A missing,
stale, corrupt, or unsupported snapshot produces a typed state and a
lifecycle-owned rebuild request.

The snapshot never serializes a complete `RawEvidenceRecord`. Raw locator
metadata omits duplicate `content`/`excerpt` factual fields,
`locator_atom_ids`, `raw_indexes`, and generic source-unit metadata. Its
`rerank_text` preserves the accepted full-unit coverage, phrase, and proximity
ordering exactly, but remains derived search material. After fusion, the active
resolver reads the selected revision's verified `source.json`, reconstructs
the requested `RawEvidenceRecord` from the matching `SourceUnitRecord`, and
validates revision, Raw revision, processing record, source record, unit, and
span identities before returning content.

`lexical_snapshot.v7` replaces v6 directly. It retains the accepted compact
letter/number tokenization and normalizes repeated derived search material:
complete parent-unit `rerank_text` is stored once per Raw evidence identity and
joined into transient locator rows when they are read. Entity and relation locator rows do not duplicate immutable evidence excerpts. Synthesis is excluded from the retrieval snapshot and remains document-navigation metadata only. Claim
locators retain only the source-unit identity and exact character span needed
to close a match to active Raw, with an excerpt only for legacy exact-text
fallback when no usable span exists. Complete Raw and semantic facts remain in
their existing immutable authorities; the snapshot is only a derived locator.

The analyzer tokenizes compact
letter/number source identities such as `rfc9110` into both the compound form
and boundary parts, so named-source scope and content predicates can be
evaluated independently. Startup detects an unsupported
published snapshot, builds and verifies a complete v7 generation from active
facts, atomically moves `CURRENT`, and only then permits old-generation
reclamation. There is no v6 reader, in-place database migration, or query-time
rebuild.

Claims and relations retain their immutable revision and source-record batch
namespace. `local_claim_id` and `local_relation_id` are never placed in a
vault-wide map. An entity may use its vault-scoped canonical entity ID, while a
relation's `source_claim_ids` resolve only within its own batch.

## Lexical Normalization And Windows

Index and query paths share one deterministic analyzer:

- Unicode NFKC, case folding, whitespace/full-width normalization;
- canonical entity aliases and clear technical-identifier equivalence;
- original Latin identifier plus camel, snake, and kebab variants;
- Chinese bigrams as primary recall tokens and trigrams as precision features;
- the normalized full phrase retained separately for phrase/proximity rerank.

Raw content is indexed as locator windows of approximately 256 lexical tokens
with 64-token overlap, preferring paragraph and sentence boundaries. Window
identity is derived and never leaves the retrieval layer as factual evidence.
All windows map to the parent `(vault_id, raw_revision_id, source_unit_id)`;
fusion and paging deduplicate at that parent identity. The resolver validates
the complete parent unit, then evidence packaging projects the matched
structure-preserving segments.

### Query Terms And BM25

The analyzer produces one immutable lexical query plan shared by both recall
channels:

- recall terms retain deterministic full phrases, CJK bigrams/trigrams, and
  Latin identifier variants;
- Chinese conversational scaffolding and connective boundaries split the
  original text before n-grams are generated;
- domain nouns such as architecture, framework, component, technology, method,
  setting, location, topic, and effect are never stop terms merely because they
  are common;
- Latin words form one anchor group, while identifiers containing digits,
  separators, CamelCase boundaries, or a stable uppercase technical form retain
  their own variant group;
- technical clauses disjoin complete variants and conjoin the original parts of
  a separated compound identity.

FTS uses the complete disjunction of ordinary recall terms and technical-anchor
clauses. Each technical clause disjoins complete variants while conjoining all
parts of a separated compound identifier. FTS exhaustively visits every matching
row and assigns its field-weighted BM25 rank without a second hand-authored
eligibility predicate. `fts_hit_count` remains the auditable match count;
`ineligible_hit_count` is retained as a compatibility diagnostic and is zero
for this baseline.

## Recall Providers

### AtomClaimRecall

Uses fielded BM25, entity alias expansion, batch-scoped relation
`source_claim_ids`, and exact claim evidence signals. Initial field-weight
seeds are claim text `4.0`, alias `3.0`, entity `2.0`, predicate `1.5`, and
allowlisted payload `0.5`. Synthesis remains a projection/source navigator and
does not produce evidence.

Claim resolution keeps one cache per `(revision_id, source_record_id)` for the
duration of the Query execution. A non-claim atom causes its active batch to be
read and validated once, then code builds both a local claim-ID map and an
entity-key-to-claims inverted map. Later entity/relation hits reuse those maps;
direct claim hits need no batch read. This preserves complete claim reachability
while preventing query cost from multiplying by atom-hit count.

### RawUnitLexicalRecall

Indexes the derived locator windows with initial field weights: title/heading
`3.0`, structural path `2.0`, content `1.0`, and source basename `0.5`.
All fields contribute through BM25 order; none is a separate eligibility gate.
It returns locator spans and parent Raw identity, not invented claims. Only exact-offset,
structure-preserving segments of explicitly selected parent units are later
sent to an answer model.

## Fusion And Paging

Each provider exposes its complete deterministic ordered match stream. Parent
Raw fusion retains every contributing signal for trace, but computes one best
rank contribution per channel with initial `k=20`, atom/claim weight `1.2`,
Raw weight `1.0`, and only bounded corroboration from additional channels.
Repeated claims or locator windows never accumulate rank merely because a
section is long or extraction-dense. BM25 scores from different corpora are
never added or normalized into a shared score. Raw locator metadata hydrates
title, path, rerank text, and page locators even when an atom signal created the
parent identity first.

Raw identity deduplication occurs while streams are consumed, before the
collection is disclosed. A handle records every contributing signal so trace
can explain its fused rank. Internal database batches may use an opaque cursor
containing the validated query fingerprint, generation, and next offset, but
the retrieval owner continues consuming it automatically.

Single-query provider streams remain completely reachable. Chat batch
retrieval consumes the first 12 fused parent candidates per region group after
BM25/RRF ordering, deduplicates them by vault-scoped Raw identity, reranks the
combined set by reciprocal-rank contribution, and retains the first 16 parents
globally. These Query-owned result windows are exposed in diagnostics; they are
not context-character budgets, confidence thresholds, or user settings.

A Query batch opens and verifies one immutable index snapshot per selected
vault. Every expression and the subsequent active Raw resolver in that batch
share that snapshot. Snapshot sharing changes neither ordering nor evidence
membership; it only removes repeated whole-generation verification from the
same request. A snapshot prepared for another vault is rejected.

The only interruption boundary while producing those ordered streams is one centralized
`RetrievalSafety` envelope over wall time, accumulated bytes, memory, provider
context, and model/tool calls. Retained lexical matches are measured from their
actual typed object graph rather than inferred from serialized metadata size.
If the envelope fires, completed rows remain available to the internal
continuation state, the collection is marked
`exhausted=false`, preserves its continuation cursor, and returns
`resource_exhausted`; it is never eligible for no-match or general answering.
An immutable index working set that cannot enumerate one ordered row within the
safety envelope returns typed non-resumable `resource_exhausted` without a
continuation cursor; an unchanged offset-zero cursor would falsely promise
progress.

Candidate ranking and answer evidence selection remain separate.
`CandidateSet` retains lightweight handles inside both the regional and global
BM25/RRF result windows. `structural_evidence.v1` performs no semantic scoring.
It selects every retained handle having at least one valid exact span from
Claim evidence, Raw lexical location, or a relation-supporting Claim. Its trace
contains only query identity, contributing channel identity, and span count.

Claim-created handles are hydrated directly from compact Raw locator metadata;
they never depend on an incidental Raw lexical hit to obtain source path,
title, active identities, or parent content used to resolve legacy evidence
excerpts. When a published Claim edge contains an excerpt but no offset, Query
locates that exact excerpt in the active parent locator text and derives the
span before structural selection.

BM25 and reciprocal-rank fusion order their respective streams. Repeated signals contribute only their best parent/channel rank.
BM25/RRF order determines the Chat result windows; no hand-authored coverage,
phrase, confidence, source-diversity, or winner rule runs afterward. This
boundary cannot prove answer completeness, so it does not attempt to.

## Active Evidence Resolution

The resolver accepts only a vault-scoped EvidenceHandle. It loads the current
source head and validates Raw revision, processing record, source unit, and
span/hash metadata. It returns the complete active unit or a typed stale,
integrity, missing, or oversized result.

Session history never restores a stored Raw payload as current evidence.
`reuse_context` stores and resubmits handles, then calls this resolver. A stale
handle may trigger a new search but cannot support an answer.

## Outcome Semantics

Per-channel statuses are `completed`, `no_candidates`, `unavailable`, `error`,
or `cancelled`. QueryOutcome is computed deterministically:

- `candidates`: at least one active handle has exact structural evidence;
- `no_match`: every required channel completed successfully and no handle
  has exact structural evidence;
- `integrity_error`: selected or required identities fail active validation;
- `index_unavailable`: the verified snapshot cannot be loaded or rebuilt;
- `invalid_query`: normalized input has no valid searchable content;
- `invalid_scope`: vault or source scope is invalid;
- `resource_exhausted`: enumeration stopped at a safety boundary before the
  ordered result stream was exhausted;
- `cancelled`: the request cancellation token was observed.

Channel `match_count` counts FTS/BM25 rows. Channel detail and query stats also
record total FTS hits and the compatibility ineligible count, which is zero
under the BM25 baseline.

Query never emits `sufficient` or `partial`. Those are answer-semantic states
owned by specification 1.10 after a model proposes dimension support and code
validates the referenced evidence identities.

`no_match` is a completed-search and structural-evidence fact. It requires a
verified snapshot matching the active fact generation, valid scope, successful
completion of both required channels for the original QueryPlan, exhausted
result streams, and zero exact evidence spans. Actual
safety interruption remains `resource_exhausted`; it is never inferred merely
because CandidateSet is non-empty while EvidenceSet is empty.

## Query And Chat Handoff

`wiki_query.v4` exposes one ordered lightweight `CandidateSet`, one selected
`EvidenceSet`, selected `EvidenceRead` values, typed QueryOutcome, optional
projection navigation, trace, gaps, warnings, and a Raw-only context pack.

Chat uses the same operations:

```text
catalog(active vault scope) -> ActiveCorpusCatalog
search(QueryPlan) -> CandidateSet
select_exact_spans(CandidateSet) -> EvidenceSet
read(EvidenceSet.handles) -> EvidenceRead[]
project(EvidenceRead[], matched_spans) -> EvidenceSegment[]
```

Linear Chat receives only the selected `EvidenceSet`. It does not receive the
candidate payload and never forks retrieval policy.

## Structure-Preserving Evidence Packaging

Candidate enumeration completes independently from structural selection and
answer-model packaging. For each selected parent Raw identity, Query merges all
matched spans from every expression and channel, resolves the complete active
unit for integrity, and projects the smallest complete structures containing
those spans. Overlapping or whitespace-adjacent structures merge; disjoint
structures remain separate under the same evidence identity. Tables, lists,
code, and formulas remain complete when intersected. Query never silently cuts
a structure, drops a matched span, substitutes a summary, or treats provider
capacity as evidence absence. Full-unit content remains locally resolvable but
is not the default answer payload.

## Document And Chapter Scoped Retrieval

The navigation index is a derived locator view, not another semantic graph:

```text
active source processing records
  -> one document region per source
  -> one region per top-level numbered or named chapter
  -> lower-level source units folded into their chapter
  -> compact active_corpus_outline.v1
```

Opaque region IDs are stable hashes of vault, source record, and chapter key.
The visible payload contains only vault, document, source type, and chapter
labels. A separate Query-owned map resolves each ID to active
`source_record_id` and `source_unit_id` membership.

The Retrieval Planner returns zero or more visible IDs and one standalone
expression per selected region. Chat creates a region group containing the
exact latest user question plus that regional expression. Query recalls
through the ordinary Raw lexical and atom/claim providers, removes
candidates outside that expression's region, then performs normal fusion,
structural selection, active resolution, and structure-preserving projection.
Variants jointly consume one 12-parent region-group window using the best rank
attained by each parent; alternative wording does not add repeated votes. The same Raw
identity reached through several regions is fused and resolved once before the
16-parent global window.

For a source without recognized chapters, its document region remains
selectable. If the planner returns no valid region or is unavailable, Chat
runs one unscoped unchanged question. No title-keyword query, community
membership, or per-candidate model judgment is invented inside Query; the
planner's regional expression is only another lexical input.

## Public Contract Replacement

`wiki_query.v4` directly replaces its development predecessor. The implementation deletes:

- atom-only `RawGroundedRetriever` runtime semantics;
- the test invariant that Raw-only terms are unreachable;
- bare non-vault-scoped evidence handles;
- eager duplicate-heavy candidate materialization that bypasses streaming and
  parent identity folding;
- per-request full collection scans after the active snapshot is available;
- graph traversal, graph-specific dependencies, path trace, and synthesis retrieval rows;
- v3 query readers, fixtures, and compatibility fields.

Retrieval generations are rebuildable, so no factual migration is required.
Development indexes are rebuilt and development query fixtures are replaced.

## Model And Code Ownership

| Element | Owner |
| --- | --- |
| region selection and one regional expression | Retrieval Planner model, validated by 1.10 |
| lexical recall and ranks | 1.38 deterministic code |
| document/chapter region resolution and filtering | 1.38 deterministic code |
| Raw identity, active revision, hashes | factual storage and 1.38 resolver |
| fusion, structural evidence selection, cursor, safety, channel status | 1.38 deterministic code |
| source attachment-to-Raw association and deduplication | 1.38 Chat evidence adapter |
| dimension support proposal | grounded answer model under 1.18 |
| support identity validation and final Chat transition | 1.10 deterministic code |
| answer prose and citations | selected synthesizer plus deterministic resolver |

Models never own vault identity, active revision, handle construction, cursor,
storage state, cancellation, or lifecycle decisions.

## Performance And Complexity

The active snapshot removes per-query full-corpus reconstruction. Only selected
parent units are reconstructed from their verified active factual revisions.
Initial
targets on a representative 10k-active-unit / 50k-atom local corpus are:

- warm retrieval p95 <= 250 ms;
- cold verified snapshot open p95 <= 1.5 s;
- candidate enumeration remains streaming/bounded-memory and every match stays
  reachable until exhaustion or a typed safety stop;
- no query-time memory growth proportional to complete conversation history.

Cold rebuild cost and index size are recorded separately from warm query
latency. Targets may change only through this owner and corresponding benchmark
evidence.

Ordering weights and resource safety defaults may be calibrated only against the fixed gold set, with
the change recorded in this owner. The runtime does not learn weights online.
Pseudo-relevance feedback is not enabled by default because a small personal
vault can drift toward an early false positive.

## Privacy And Security

Retrieval remains local and model-free. Raw lexical documents are derived local
index material under the same backup and data boundary as other machine index
artifacts. Only selected structure-preserving Raw segments cross the configured
answer-model boundary. The complete candidate payload and unrelated portions
of selected Raw units remain local to Query; trace and
locators do not broaden the factual payload.

## WeKnora Mechanism Decisions

| Mechanism | Decision | KnoArbor adaptation |
| --- | --- | --- |
| conditional query understanding/rewrite | Adopt | 1.10 plan provider, not mandatory `/query` model call |
| parallel recall channels | Adopt | atom/claim and active Raw lexical providers |
| ordered recall and staged rerank | Adopt | complete channel streams, deterministic fusion and rerank |
| retrieval references separate from inline citations | Adopt | EvidenceCollection versus final cited evidence |
| giant shared mutable Chat state | Reject | immutable typed stage values |
| silent rerank fallback or threshold lowering | Reject | typed channel failure and explicit low-confidence result |
| every request runs full pipeline | Reject | shared fast/progressive retrieval session |
| automatic assistant-answer indexing | Reject | provenance-gated Chat ingest |
| dense recall, cross encoder, Web Search | Defer | require evaluation or separate source contract |
| default pseudo-relevance feedback | Reject | unacceptable topic-drift risk in small personal corpora |

## Rejected Alternatives

### Atom-Only Recall

Rejected because missing extraction becomes indistinguishable from knowledge
absence.

### Independent Raw Fallback

Rejected because it creates a second policy and untyped score merge.

### Page-First Retrieval

Rejected because projections remain derived presentation.

### Lexical Score As Semantic Sufficiency

Rejected because relevance ranking cannot prove that evidence answers a natural
language dimension.

### Preserve V2 Query Compatibility

Rejected because the development-stage contract lacks channel status,
vault-scoped handles, stable cursor, and trustworthy no-match.

### Runtime Lexical Fallback

Rejected because per-request BM25 or a second postings scorer would make
ranking and no-match depend on the runtime environment rather than one verified
snapshot contract.
