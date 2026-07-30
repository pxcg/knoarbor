# 1.38 Unified Active Raw Evidence Retrieval Verification

## Lifecycle

Accepted; lexical retrieval closure evidence passed and the cross-source
relation verification remains in progress.

## Current-State Reproduction (2026-07-25)

The fixed six-document desktop corpus exposes why semantic atoms are unsuitable
as the first navigation payload: Claims, Entities, Relations, and derived
communities grow much faster than source structure. Exposing all first- and
second-level headings likewise produced 350 regions and about 30,146 serialized
characters. Folding lower-level headings into top-level chapter regions yields
55 chapter regions plus six document regions and 5,641 serialized characters,
without hiding any source unit from its enclosing document region.

## Focused Commands

```bash
uv run python -m unittest \
  tests.test_query_text \
  tests.test_retrieval_quality_gold \
  tests.test_semantic_indexed_query \
  tests.test_query_batch \
  tests.test_api_surface \
  tests.test_cli \
  tests.test_skill_query_helper \
  tests.test_chat_knowledge_tools \
  tests.test_chat_evidence \
  tests.test_chat_agent
```

Add focused snapshot, fusion, cursor, benchmark, cancellation, and multi-vault
tests under their owning modules as implementation files appear. Full discovery,
`dev-check.sh`, desktop packaging, and live-model checks are not automatic R3
closure commands; escalate only when the actual dependency closure or a release
checkpoint reaches them.

## Contract And Identity Assertions

- Outline identity and ordering are deterministic for the same active source
  records.
- Each active source-level synthesis appears once and in full on its document
  node, including multiline content; it is not copied into chapter nodes.
- Raw, individual Claim/Entity/Relation rows, attachments, and internal
  revision/evidence identities do not enter the visible outline.
- A selected region adds one normal Query expression containing the unchanged
  question and limits only that expression's candidates.
- Empty, unknown, or unavailable navigation leaves one unscoped unchanged
  query.
- The scoped implementation changes no ingest implementation or contract.

1. `wiki_query.v4` is the only accepted query schema; v2 payloads and fixtures
   are rejected.
2. Every handle includes vault, active revision, and source-unit identity.
3. Equal local IDs in two vaults remain distinct through recall, read, citation,
   and Chat state.
4. Mixed CJK questions around a fully matched two-part Latin identity retrieve
   the intended Raw unit; one-part and partial identity matches do not bypass
   eligibility.
5. Retrieval-quality fixture paths contain no expected query anchors, isolated
   channels demonstrate their intended gaps, and merged retrieval retains the
   accepted perfect expected-source metrics while outperforming both channels.
6. Equal batch-local claim/relation IDs in two sources remain distinct and a
   relation resolves `source_claim_ids` only inside its own source-record batch.
7. Atom and Raw signals for one unit fuse into one handle with both trace paths.
8. Retrieved handles, read evidence, and cited evidence remain separate typed
   collections.
9. The BM25/RRF-windowed lightweight `CandidateSet` and selected structure-preserving
   `EvidenceSet` are distinct typed collections.
10. A stored historical handle is re-resolved; a stale revision cannot return
   its persisted Raw payload.
11. The outline contains deterministic region IDs, document/chapter display
    metadata, and exactly one complete locator-only synthesis per document.
12. Region resolution maps to active source record and source unit identities
    that are not exposed to the model.

## Recall And Outcome Assertions

1. Direct claim, entity alias, and relation cases retain current recall.
2. A Raw-only extraction-miss case is found through Raw lexical recall.
3. A Raw locator window highlights its local match, resolves the complete
   active parent SourceUnit for integrity, and projects exact-offset complete
   local structures for answer evidence.
4. Projection prose and graph links do not produce factual evidence.
5. A matching candidate below former top-k boundaries remains reachable and is
   folded into its parent Raw identity.
6. Cursor reuse with another query, scope, or retrieval generation fails explicitly.
7. `no_match` requires successful completion and exhaustion of all required channels.
8. Index absence, integrity mismatch, invalid scope, tool failure, and
   cancellation never become no-match.
9. Every matched span remains represented after parent deduplication; prose,
   table, list, code, and formula structures are never arbitrarily truncated or
   summarized, and projected offsets reproduce the exact Raw substring.
10. CJK bigram/trigram/phrase and Latin identifier variants are deterministic
    and identical at index and query time.
11. FTS5 unavailability never invokes the former in-memory scorer.
12. Wall-time, byte, memory, context, or call safety exhaustion returns
    `resource_exhausted` with continuation state and never no-match.
13. Internal database batch size changes do not change the complete ranked
    candidate set.
14. Conversational scaffolding is removed, while content-bearing domain nouns
    remain BM25 terms.
15. FTS matches are ordered by field-weighted BM25 without a second
    concept-anchor eligibility predicate.
16. Channel stats distinguish total FTS hits from eligible matches and excluded
    weak hits, and a weak-hit-only exhausted search may produce no-match.
17. A compound technical identifier does not match on one colliding numeric or
    alphabetic component; a complete variant or all original parts remains
    reachable.
18. Materialized-match memory is accounted from retained typed values; repeated
    offset/rank continuations reproduce the unlimited ordered result exactly.
19. Source identity, title, structure, and body content contribute through
    explicit BM25 field weights rather than Boolean source authorization.
20. Broad and comparative queries preserve disjunctive lexical recall and use
    BM25/RRF order to form each Chat expression's result window.
21. Quoted Chinese titles remain full-phrase BM25 terms but do not create a
    separate required-anchor gate.
22. Raw locator rows contain no serialized `content`, `excerpt`,
    `locator_atom_ids`, `raw_indexes`, or generic source-unit `metadata`;
    complete rerank text preserves ordering while selected evidence content is
    reconstructed from the verified active factual revision.
23. Tampered or stale locator payload cannot become answer evidence; active
    revision, Raw revision, processing record, source record, unit, and spans
    are validated at read time.
24. A published v3 snapshot is unsupported to readers and the startup
    materializer atomically replaces it with v4 without changing active facts.
25. The complete single-query provider stream remains reachable; the Chat batch
    retains the first 12 BM25/RRF-ordered parent candidates per region group,
    deduplicates by vault-scoped Raw identity, and retains the first 16
    candidates globally.
26. Every retained candidate with a valid exact Claim, Raw locator, or
    relation-support span enters EvidenceSet; no later expression winner,
    confidence threshold, or source-diversity rule controls membership.
27. Repeated claim or locator-window signals do not increase a parent unit's
    channel rank contribution, and atom-first parents receive Raw title, path,
    and rerank metadata before final scoring.
28. Chat receives only `EvidenceSet`, while candidate count and compact outcome
    trace remain diagnostic metadata without candidate Raw or locator payloads.
29. Multiple entity/relation atom hits in one source read and validate that
    source's atom batch once, while direct claim hits require no batch read.

## Gold Quality Gates

The versioned gold set covers direct claims, aliases, relations, Raw-only
facts, synonymous paraphrases, CJK phrases, technical identifiers,
multi-dimensional questions, true out-of-scope questions, inactive revisions,
corrupt edges, duplicate units, multi-vault collisions, and oversized units.

Record:

- active Raw-unit Recall@20, MRR, and nDCG;
- no-match precision;
- selected exact-span identity and offset integrity;
- claim-backed baseline delta;
- evidence identity and span integrity;
- eligible/retained candidate counts, per-expression result windows, and pagination;
- cold/warm latency, peak memory, and snapshot size.

Acceptance gates:

- active identity and citation-span integrity: 100%;
- emitted no-match precision: at least 95% Wilson lower bound before general
  fallback is enabled, with false no-match on knowledge-present queries
  separately no greater than 5%;
- every Raw-only gold fact is reachable;
- claim-backed Recall@20 regression is no more than two percentage points;
- merged Recall@20 exceeds each single channel;
- selected exact-span identity and offset integrity is 100%;
- complete single-query provider reachability, Chat result-window membership,
  and safety-state transitions are exact.

Chat-linked gates additionally require false general-answer routing no greater
than 5%, coverage-support precision at least 95%, and coverage-support recall at
least 90%. Every report includes sample size and a 95% confidence interval; if
the accepted set is too small to support the no-match claim, general routing
remains disabled.

The accepted `knoarbor-no-match-gold-2026-07-18` routing calibration contains
100 knowledge-present and 100 knowledge-absent queries. Under the BM25-ranked
baseline, all 100 present queries remain candidates; 79 absent queries emit
no-match and 21 conservatively retain weak lexical candidates. Emitted
no-match precision is `1.0` over 79 outcomes with Wilson 95% confidence
interval `[0.9536287883, 1.0]`; false general routing remains `0.0` over 100
present queries with interval `[0.0, 0.0369934982]`.

## Performance Gates

On the accepted representative corpus of approximately 10k active units and
50k atoms:

- warm retrieval p95 <= 250 ms;
- cold verified snapshot open p95 <= 1.5 s;
- query memory remains bounded by snapshot streaming and RetrievalSafety rather than
  complete Chat history;
- rebuild produces deterministic generation manifests and equivalent results.
- on the accepted six-document desktop corpus, Raw locator metadata is at most
  15 MiB and at least 90% smaller than the v3 baseline, the complete retrieval
  database is at most 90 MiB, and Raw/atom/relation row counts are unchanged.
- the retained six-document NASA long-source query completes the model-free
  batch in under 1.5 seconds while selecting the expected NASA Raw source.

These are initial engineering targets. Any calibrated change belongs in this
owner with new benchmark evidence.

## Chat Boundary Assertions

- Linear Chat calls the same QueryPlan search, structural selection, and selected
  EvidenceHandle read operations.
- Query never declares `sufficient` or `partial`.
- Chat does not rerank, filter, or truncate Query-selected evidence segments.
- Query gaps, warnings, channel status, and integrity failures survive Chat
  projection unchanged.
- Query exposes typed candidate/no-match outcomes without choosing Final
  Answer authority; the unified Final Answer contract owns that semantic
  choice.

## Documentation And Cleanup

```bash
python3 scripts/check-doc-governance.py
python3 scripts/check-doc-links.py
git diff --check
```

Closure review confirms no atom-only runtime, v2 query reader, direct Raw
fallback, eager duplicate-heavy candidate materialization, bare evidence
identity, stale Raw reuse, or compatibility flag remains.


## Document And Chapter Navigation Gates

The scoped navigation revision must prove:

1. the visible outline contains documents, each document's complete synthesis (absent from atom FTS and evidence),
   top-level chapters, and opaque region IDs but no Raw, individual
   Claim/Entity/Relation rows, attachment, storage, revision, or evidence
   content;
2. lower-level source units belong to their top-level chapter region;
3. every selected region receives the unchanged question and at most one
   standalone regional expression under a shared 12-parent group window;
4. a parent matched by both alternative expressions receives one best-rank
   contribution and cannot displace a more specific parent through duplicate
   voting;
5. a region excludes candidates from source units outside that region before
   fusion and structural selection;
6. multi-region results deduplicate one active Raw identity reached more than
   once;
7. invalid model-selected IDs are retried and empty/unavailable planning
   runs one unscoped unchanged query;
8. the retained six-document outline remains compact relative to exposing all
   Claim/Entity/Relation rows or second-level headings;
9. only image attachments directly referenced by selected Raw units enter the
   answer packet, each at most once;
10. Ingest facts, schemas, prompts, and materialization are unchanged.

## Structure-Preserving Evidence Packet Shadow Comparison (2026-07-25)

The 25 retained six-document retrieval cases were replayed from their recorded
query expressions without invoking the final answer model. Candidate status,
candidate count, and selected Raw identity/count were unchanged in every case.
The existing complete-unit answer payload contained `7,332,219` characters;
the structure-preserving packet projection contained `7,182,461`, a `2.0%`
aggregate reduction. Median per-case characters fell from `66,683` to `34,002`,
but `4,642 / 4,718` selected units (`98.4%`) were already fully covered by
their matched windows, accounting for `94.8%` of complete-unit characters.

This evidence rejected read-granularity change as a sufficient standalone fix.
The follow-up root repair removed post-fusion semantic scoring, selected every
exact structural span, and completed the Chat segment cutover. The historical
character counts remain a baseline; they are not evidence for the new
membership semantics. No missing-span fallback occurred in this shadow run.

## Closure Evidence

The 2026-07-26 v6 storage and batch-cost closure rebuilt a disposable clone of
the retained six-document corpus. `retrieval.sqlite` fell from `88,662,016` to
`45,158,400` bytes (`49.1%`) while preserving `1,551` parent Raw rerank units
and exact API hydration. Focused tests prove that multi-expression batches
open one snapshot per vault, Raw locator rows no longer repeat parent rerank
text, compact atom locators preserve Claim closure, and active processing
records are read once per evidence vault rather than once per evidence row.
The current v7 Query path replayed all 40 retained cases having recorded
expressions: 39 returned candidates, one returned trustworthy no-match, and
434 active evidence reads completed in `12.634 s`. A row-for-row comparison
against the retained v5 fixture confirmed identical retrieval identities, FTS
search fields, relation edges, and relation-support payloads; only normalized
derived metadata and its schema marker differ.

The 2026-07-18 closure ran the specified focused suite (131 tests), all 630
Python tests, Ruff, architecture governance, documentation links/governance,
and the renderer production build successfully. The representative 10,000 Raw
unit / 50,000 atom benchmark recorded warm two-channel p95 `18.164 ms`, cold
verified snapshot p95 `182.291 ms`, and zero wrong query statuses. Default
materialized-memory safety stopped the broad result stream at 19,418 ordered
matches with an opaque continuation cursor and a `61,518,485` byte tracemalloc
peak under the 64 MiB limit; focused tests proved query and generation binding
plus complete continuation order.

The 2026-07-23 compact-v4 closure rebuilt the retained six-document desktop
corpus into a disposable target without modifying its facts or published
generation. Raw locator rows remained `3,012`, atom rows `8,990`, and relation
edges `1,822`; Raw metadata fell from `219,552,861` to `12,634,828` characters
(`94.2%`), and the complete SQLite snapshot fell from `291,856,384` to
`84,316,160` bytes (`71.1%`). Five real-corpus query probes completed in
`4.760`–`64.094 ms`, including factual reads from verified revisions. The
mechanically selected 490-test dependency closure, all 780 Python tests, Ruff,
architecture governance, documentation governance/links, and diff whitespace
validation passed.

