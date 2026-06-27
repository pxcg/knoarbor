# 1.13 Knowledge Atom Ingest Tasks

## Ingest Chain Progress

This table is the active implementation tracker for the claims-first ingest
refactor. It maps the end-to-end ingest chain to concrete ownership boundaries
so progress does not depend on conversation context.

| Step | Boundary | Status | Owner / Output | Notes |
| --- | --- | --- | --- | --- |
| 1 | Source Input | Frozen | Connectors, document processors, `SourceDocument`, checkpoint identity | Raw materials become normalized source documents with source identity, raw state, fingerprint, stable session raw indexes, and checkpoint windows. |
| 2 | Source Segmentation + Source Unitization | Frozen | `SourceSegmenter`, `SourceUnitizer` | Segmentation splits long sources for budget. Unitization produces source-native evidence spans for source digests and atoms. Neither boundary decides page boundaries or writes. |
| 3 | Segment-level Semantic Extraction | Frozen | `source_normalize`, `wiki_atom_extract`, `knowledge_atoms.v2` | Extract claims, entities, relations, and evidence from each source or segment. This is where claims are created. |
| 4 | Source-level Aggregation | Frozen | `AggregatedSemanticArtifacts` | Merge segment extracts, remap evidence ranges, deduplicate atoms, rebuild source-level digest audit data, and emit source-level atom quality. |
| 5 | Page Planning + Graph Alignment | Frozen | `WikiPagePlan` | Decide create/update/skip, select claim ids per page, reconcile entity names with candidate profiles, and place supported relation ids across page operations. Retrieval, writes, and page body assembly stay in their own stages. |
| 6 | Claim / Relation / Evidence Closure | Frozen | `knowledge_atom_closure` | Given selected claims, deterministically close supported relations, entities, evidence, and source digest traces. |
| 7 | Page Assembly / Draft Compile | Frozen | `PageAssemblyService` + page-local prose generation | Assemble identity, claims, relations, entities, evidence, and Markdown skeleton deterministically; use LLM mainly for summary, synthesis, and safe update prose. |
| 8 | Review / Write Gate | Frozen | `IngestWriteGate`, draft review agent, ingest report renderer | Deterministic write gate is separate from semantic review; semantic review is conditional on risk signals, and reports expose both decisions independently. |
| 9 | Write / Report / Index | Frozen | `IngestPostProcessor`, `WikiWritePipeline`, atom index, graph/manifest reports | Persist approved pages, refresh indexes, run scoped maintenance, commit checkpoints, and emit reports without creating new semantic decisions. |

Step 2 has one implemented boundary and one frozen implementation target:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 2.1 | Segment Source | `SourceDocument` | `SourceSegmentBatch` | Code |
| 2.2 | Unitize Source | `SourceDocument` or `SourceSegment` | deterministic source units + warnings | Code |

Segmentation is an execution and budget boundary. Unitization is an evidence and
audit boundary. The detailed contract is frozen in
[Source Unitization Boundary](source-unitization-boundary.md). Source-type unit
boundaries are produced by deterministic code and then passed to source
normalization as the evidence contract. Remaining matrix entries, such as
image OCR region units, are explicit future source-type extensions rather than
semantic-agent responsibilities.

Step 3 is frozen as four named substeps. Use these names in code review,
implementation notes, and future SDD updates:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 3.1 | Normalize Source Segment | `SourceDocument` | `KnowledgeExtract` | Model |
| 3.2 | Build Source Digest Audit | `KnowledgeExtract` | `SourceDigest` | Code |
| 3.3 | Extract Knowledge Atoms | `SourceDigest` | `KnowledgeAtomBatch` | Model |
| 3.4 | Validate Knowledge Atoms | `KnowledgeAtomBatch` | `KnowledgeAtomQualityReport` | Code |

The step boundary is claims-first: claims are created only in 3.3. Step 3 does
not decide page identity, page write action, Markdown page body, or checkpoint
commit eligibility.

Step 3 artifacts are first-class outputs:

- `KnowledgeExtract` preserves normalized source units after semantic cleanup.
- `SourceDigest` provides the data layer for source digest audit pages:
  source identity, code-generated audit summary, source units, raw source
  pointer, source-level unresolved items, and later contribution-map fields.
- `KnowledgeAtomBatch` carries claims, entities, relations, and evidence.
- `KnowledgeAtomQualityReport` records unsupported, conflicting, duplicate, or
  unused atom signals before page planning.

Step 4 is frozen as deterministic source-level aggregation. It receives one or
more Step 3 artifact groups and emits a single source-level contract for page
planning:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 4.1 | Merge Source Units | segment `KnowledgeExtract` list | source-level `KnowledgeExtract` | Code |
| 4.2 | Rebuild Source Digest Audit | source-level `KnowledgeExtract` + atoms + write/result facts | enriched `SourceDigest` | Code |
| 4.3 | Merge Knowledge Atoms | segment `KnowledgeAtomBatch` list | source-level `KnowledgeAtomBatch` | Code |
| 4.4 | Validate Aggregated Atoms | source-level `KnowledgeAtomBatch` | source-level `KnowledgeAtomQualityReport` | Code |

Step 4 does not call an LLM. It must preserve segment provenance, remap evidence
unit indexes, deduplicate equivalent claims and relation triples, and expose
pending source contributions without choosing target pages.

Step 5 is frozen as claims-first page planning with page-level graph alignment.
It receives the source-level digest, source-level atoms, deterministic
lightweight candidate profiles, and the schema-level relation vocabulary, then
emits page operations plus bounded normalization decisions attached to those
operations:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 5.1 | Build Candidate Profiles | source-level atoms + graph/text indexes | `IngestWikiContext` | Code |
| 5.2 | Plan Page Operations and Graph Alignment | `SourceDigest` + `KnowledgeAtomBatch` + candidate profiles + allowed predicates | `WikiPagePlan` | Model |
| 5.3 | Validate Page Plan Contract | `WikiPagePlan` + atoms | validated `WikiPagePlan` | Schema / Code |

Every actionable operation must carry `source_digest_ids`. Every non-source
operation must select at least one claim atom id. Relation ids are auxiliary and
cannot replace selected claims. Step 5 may map local entity names to canonical
entity names already visible in atoms or candidate profiles. Step 5 may attach
selected relation ids to existing or newly planned page targets when the
relation has supporting selected claims. Full target, related, and candidate
content is loaded after planning.

Graph alignment is implemented inside Step 5 rather than as a new model stage.
The model decision is limited to page boundary, update target, atom selection,
entity canonicalization choices, and relation placement. Deterministic services
apply and verify those choices:

| Check | Owner | Required behavior |
| --- | --- | --- |
| Predicate vocabulary | Schema / code | Relation predicates use the `KnowledgeRelationPredicate` vocabulary. |
| Entity mapping | Code | Canonical names are selected from current atoms or candidate page profiles; aliases remain traceable. |
| Cross-page relation support | Closure / write gate | Relation ids must bind to selected or explicitly carried supporting claim ids. |
| Candidate page provenance | Schema / code | Candidate and target paths come from the deterministic candidate pool or the current create plan. |
| Page body projection | Page assembly | Claims, entities, relations, and evidence rows are projected from validated atoms and mappings. |

The Step 5 output contract should evolve without adding a new ingest stage:

- `entity_mappings`: operation-local mapping from extracted names or aliases to
  canonical entity names and optional existing page paths;
- `relation_mappings`: operation-local mapping from selected relation ids to
  canonical subject, predicate, object, and target page context;
- `cross_page_relations`: operation-local relation placements that connect the
  current page operation with another existing or newly planned page.

These fields are planning metadata. Selected atom ids remain the durable
knowledge trace and the atom extraction surface remains Step 3.

Step 6 is frozen as deterministic claim closure. It receives the page plan and
source-level atom batch, then produces only the atom subset that can safely
support later page assembly:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 6.1 | Validate Selected Claim Trace | `WikiPageOperation` + `KnowledgeAtomBatch` | claim ids + closure issues | Code |
| 6.2 | Close Supported Relations | selected claim ids + relation atoms | relation ids + relation issues | Code |
| 6.3 | Close Entities and Evidence | selected claims + closed relations | entity names + evidence spans | Code |
| 6.4 | Carry Source Digest Trace | operation source digest ids + evidence spans | source digest ids | Code |
| 6.5 | Build Selected Atom Batch | operation closures | scoped `KnowledgeAtomBatch` | Code |

The closure is claims-first. A relation may enter the selected atom batch only
when all its source claims are selected by the same operation. Explicit relation
ids from page planning are treated as requests, not authority. Invalid selected
claim ids or relation ids are reported as closure issues and must be blocked by
the deterministic write gate before write. Source digest id presence is
already enforced by page planning and draft write gates; cross-object source
digest existence belongs to the source digest contract rather than atom closure.

Step 9 is frozen as the deterministic write, index, and reporting boundary. It
receives only operation indexes that passed semantic review and
`IngestWriteGate`, then records what actually happened:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 9.1 | Build Approved Write Items | approved operation ids + drafts | `WikiDraftBatchWriteItem[]` | Code |
| 9.2 | Apply Write Policy | write items | canonicalized write items + policy changes | Code |
| 9.3 | Commit Pages | canonicalized write items | `WikiDraftWriteResponse[]` + generated pages | Code |
| 9.4 | Refresh Machine Indexes | written pages + vault content | generated views, machine pages, graph index, manifest | Code |
| 9.5 | Upsert Atom Index | source-level atom batches + written page refs | `.knoarbor/index/knowledge_atoms.jsonl` | Code |
| 9.6 | Scoped Maintenance | touched pages | scoped deterministic lint result | Code |
| 9.7 | Commit Checkpoint | successful written/skipped source result | checkpoint state | Code |
| 9.8 | Emit Reports and Ledgers | run result | report, run ledger, token ledger, execution ledger | Code |

Step 9 does not create claims, choose page boundaries, revise semantic content,
or reinterpret write safety. Page writes and index writes are distinct facts:
reports must preserve generated page paths even if a later index step fails.

## P0 Atom Contract

- [x] Create SDD requirements, design, tasks, and verification.
- [x] Add `knowledge_atoms.v2` schema for entities, claims, relations, and
  evidence.
- [x] Add unit tests for schema validation and atom summary counts.
- [x] Add atom contract exports to public internal schema package.

## P1 Source Digest Boundary

- [x] Split current source normalization output into source normalization and
  source digest concepts.
- [x] Keep source digest focused on source identity, stable source units, and
  evidence spans.
- [x] Add compatibility bridge from current `KnowledgeExtract` to
  `SourceDigest`.
- [x] Update source digest report payloads without changing existing page
  output.
- [x] Add rich-document attachment boundary: source digest Markdown displays
  only topic, description, and path, while sidecar metadata keeps raw image
  extraction, page regions, MIME type, and hashes.

## P1A Source Unitization Boundary

- [x] Freeze Source Unitization as a distinct SDD boundary between
  segmentation and source normalization.
- [x] Freeze the mature source-type matrix for Markdown/document, parsed
  PDF/Office Markdown, chat, agent records, Hermes conversation, selected
  excerpt, plain text, code, web/HTML, table/CSV, and image OCR sources.
- [x] Add deterministic Markdown/document heading unitization.
- [x] Add deterministic PDF/Office parsed Markdown heading, page-span, table
  block, and figure-caption unitization.
- [x] Add deterministic chat turn-group unitization for Codex, Claude Code,
  OpenClaw, and Hermes sources.
- [x] Add selected excerpt and plain text paragraph/full-source unitization.
- [x] Add web/HTML heading and article-section unitization.
- [x] Add table/CSV sheet, table, and row-group unitization.
- [ ] Add image OCR block and page-region unitization.
- [x] Add code file function/class/comment-block unitization when code becomes a
  core source type.
- [x] Pass source unit hints into source normalization and source digest
  projection.
- [x] Add report fields for source unit count, unitization rule, fallback rule,
  and unitization warnings.
- [x] Add tests proving segment count and source unit count can differ.

## P1B Rich Document Attachments

- [x] Materialize MinerU native response images from base64 payloads into
  generated Markdown `images/` folders.
- [x] Record image attachments in `*.attachments.json` sidecars.
- [x] Preserve MinerU image caption, raw extracted content, subtype, page index,
  and bounding box in attachment metadata.
- [x] Keep source digest and wiki Markdown attachment views compact:
  `Topic | Description | Path`.
- [x] Prevent raw Mermaid/OCR/model output from being inlined into default wiki
  page bodies.

## P2 Atom Extraction

- [x] Add `wiki_atom_extract_agent` prompt and semantic runner method.
- [x] Insert atom extraction after source digest and before page planning.
- [x] Add write gate checks for unsupported claims and relations.
- [x] Add report fields for extracted entity, claim, relation, and evidence span
  counts.
- [x] Add report fields for rejected, unsupported, and conflicting
  atom counts.

## P3 Page Planning

- [x] Use `WikiPagePlan` as the ingest page-planning contract.
- [x] Make page planning consume atom batches plus existing page context.
- [x] Record atom ids selected for each page operation.
- [x] Keep old page output behavior during the migration window.

## P4 Page Draft Compile

- [x] Make draft compile prompt consume page plan plus selected atom ids.
- [x] Require major page claims to reference atoms or source evidence.
- [x] Add page metadata for source digest ids and atom ids.
- [x] Update Markdown templates to expose Summary, Claims, Entities,
  Relations, Evidence, and Synthesis instead of centering on old Answer
  prose.
- [x] Pass selected claim, relation, and source digest ids through the
  shared ingest compile context.
- [x] Update draft review scoring from directory fit to source trace, atom
  coverage, identity fit, synthesis quality, and update safety.
- [x] Add deterministic write-gate checks for missing source digest trace and
  missing non-source atom trace before write.

## P5 Index, Lint, Query, Chat

- [x] Add JSONL atom index writer and reader.
- [x] Add lint checks for orphan atoms, unsupported claims, and contradictions.
- [x] Expose atom trace in ingest reports and readable frontend reports.
- [x] Allow query/chat traces to show page-to-atom evidence when available.

## P6 Ingest Agent Boundary Refactor

- [x] Freeze first-principles ingest agent ownership in
  `agent-boundary.md`.
- [x] Add graph-first ingest candidate provider before page planning.
- [x] Keep text/BM25 candidate retrieval as supplemental retrieval.
- [x] Extract `IngestSemanticRunner` so source execution does not own the
  semantic agent chain.
- [x] Extract `IngestPostProcessor` so approved writes, atom-index updates, and
  scoped lint do not live inside source execution.
- [x] Move checkpoint commit eligibility into `ingest_checkpoint`.
- [x] Rename ingest agent-facing page profiles from old key-point/tag
  language to claim/entity language.
- [x] Enforce claims-first page planning and write-gate invariants for
  non-source pages.
- [x] Aggregate segmented source atoms before page planning so long sources are
  planned and written from a source-level view.
- [x] Add deterministic claim/relation/evidence closure as a reusable service.
- [x] Add deterministic `PageAssemblyService` for identity, entities,
  relations, evidence, and Markdown skeleton.
- [x] Narrow `wiki_draft_compile` into page-local prose-generation behavior.
- [x] Add deterministic `IngestWriteGate` before persistence.
- [x] Remove source digest audit page writing from page planning and draft
  compilation.
- [x] Generate source digest audit Markdown from source units, selected atoms,
  write results, unresolved items, and raw pointers.
- [x] Narrow `wiki_draft_compile` payloads so the model receives selected page
  scaffolds, not source digest audit pages or broad source text.
- [x] Make semantic draft review conditional on update, conflict, duplicate,
  weak evidence, low-confidence, or structural-risk signals.
- [x] Separate deterministic gate decisions and semantic review decisions in
  ingest reports.

## Deferred

- [ ] SQLite atom index provider.
- [ ] RDF or graph database export.
- [ ] User-facing atom editor.
- [ ] LLM-based contradiction adjudication beyond reportable signals.
