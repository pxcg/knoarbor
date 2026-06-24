# 1.13 Knowledge Atom Ingest Tasks

## Ingest Chain Progress

This table is the active implementation tracker for the claims-first ingest
refactor. It maps the end-to-end ingest chain to concrete ownership boundaries
so progress does not depend on conversation context.

| Step | Boundary | Status | Owner / Output | Notes |
| --- | --- | --- | --- | --- |
| 1 | Source Input | Frozen | Connectors, document processors, `SourceDocument`, checkpoint identity | Raw materials become normalized source documents with source identity, raw state, fingerprint, stable session raw indexes, and checkpoint windows. |
| 2 | Source Segmentation | Done | `SourceSegmenter` | Long sources are split for budget and source-range preservation. Segmentation does not decide page boundaries or writes. |
| 3 | Segment-level Semantic Extraction | Done | `source_normalize`, `wiki_atom_extract`, `knowledge_atoms.v2` | Extract claims, entities, relations, and evidence from each source or segment. This is where claims are created. |
| 4 | Source-level Aggregation | Done | `AggregatedSemanticArtifacts` | Merge segment extracts, remap evidence ranges, deduplicate atoms, rebuild source-level digest, and emit source-level atom quality. |
| 5 | Page Planning | Implemented, needs review under new page structure | `WikiPagePlan` | Decide create/update/skip and select claim ids per page. It should not write or assemble page bodies. |
| 6 | Claim / Relation / Evidence Closure | Done | `knowledge_atom_closure` | Given selected claims, deterministically close supported relations, entities, evidence, and source digest traces. |
| 7 | Page Assembly / Draft Compile | Pending | `PageAssemblyService` + narrowed synthesis generation | Assemble identity, claims, relations, entities, evidence, and Markdown skeleton deterministically; use LLM mainly for synthesis. |
| 8 | Review / Quality Gate | Partial | `IngestQualityGate`, draft review agent | Split deterministic write gate from semantic review and make review conditional on risk signals. |
| 9 | Write / Report / Index | Partial | `IngestPostProcessor`, atom index, graph/manifest reports | Persist pages, update indexes, emit reports, and expose atom trace consistently. |

Step 3 is frozen as four named substeps. Use these names in code review,
implementation notes, and future SDD updates:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 3.1 | Normalize Source Segment | `SourceDocument` | `KnowledgeExtract` | Model |
| 3.2 | Build Source Digest | `KnowledgeExtract` | `SourceDigest` | Code |
| 3.3 | Extract Knowledge Atoms | `SourceDigest` + `KnowledgeExtract` | `KnowledgeAtomBatch` | Model |
| 3.4 | Validate Knowledge Atoms | `KnowledgeAtomBatch` | `KnowledgeAtomQualityReport` | Code |

The step boundary is claims-first: claims are created only in 3.3. Step 3 does
not decide page identity, page write action, Markdown page body, or checkpoint
commit eligibility.

Step 3 artifacts are first-class outputs:

- `KnowledgeExtract` preserves normalized source units after semantic cleanup.
- `SourceDigest` provides the data layer for source digest audit pages:
  source identity, source summary, source units, raw source pointer,
  source-level unresolved items, and later contribution-map fields.
- `KnowledgeAtomBatch` carries claims, entities, relations, and evidence.
- `KnowledgeAtomQualityReport` records unsupported, conflicting, duplicate, or
  unused atom signals before page planning.

Step 4 is frozen as deterministic source-level aggregation. It receives one or
more Step 3 artifact groups and emits a single source-level contract for page
planning:

| Substep | Name | Input | Output | Execution |
| --- | --- | --- | --- | --- |
| 4.1 | Merge Source Units | segment `KnowledgeExtract` list | source-level `KnowledgeExtract` | Code |
| 4.2 | Rebuild Source Digest Audit | source-level `KnowledgeExtract` + atoms | enriched `SourceDigest` | Code |
| 4.3 | Merge Knowledge Atoms | segment `KnowledgeAtomBatch` list | source-level `KnowledgeAtomBatch` | Code |
| 4.4 | Validate Aggregated Atoms | source-level `KnowledgeAtomBatch` | source-level `KnowledgeAtomQualityReport` | Code |

Step 4 does not call an LLM. It must preserve segment provenance, remap evidence
unit indexes, deduplicate equivalent claims and relation triples, and expose
pending source contributions without choosing target pages.

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

## P2 Atom Extraction

- [x] Add `wiki_atom_extract_agent` prompt and semantic runner method.
- [x] Insert atom extraction after source digest and before page planning.
- [x] Add quality gate checks for unsupported claims and relations.
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
  Relations, Evidence, and Synthesis instead of centering on legacy Answer
  prose.
- [x] Pass selected claim, relation, and source digest ids through the
  shared ingest compile context.
- [x] Update draft review scoring from directory fit to source trace, atom
  coverage, identity fit, synthesis quality, and update safety.
- [x] Add deterministic quality-gate checks for missing source digest trace and
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
- [x] Rename ingest agent-facing page profiles from legacy key-point/tag
  language to claim/entity language.
- [x] Enforce claims-first page planning and quality-gate invariants for
  non-source pages.
- [x] Aggregate segmented source atoms before page planning so long sources are
  planned and written from a source-level view.
- [x] Add deterministic claim/relation/evidence closure as a reusable service.
- [ ] Add deterministic `PageAssemblyService` for identity, entities,
  relations, evidence, and Markdown skeleton.
- [ ] Narrow `wiki_draft_compile` into synthesis-generation behavior.
- [ ] Add deterministic `IngestWriteGate` before persistence.
- [ ] Make semantic draft review conditional on risk, update, conflict,
  duplicate, or failed-gate signals.
- [ ] Separate deterministic gate decisions and semantic review decisions in
  ingest reports.

## Deferred

- [ ] SQLite atom index provider.
- [ ] RDF or graph database export.
- [ ] User-facing atom editor.
- [ ] LLM-based contradiction adjudication beyond reportable signals.
