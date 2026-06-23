# 1.13 Knowledge Atom Ingest Requirements

## Problem

KnoArbor currently compiles raw sources into structured Markdown pages. The
pages are readable, but the durable knowledge boundary is still too close to
free-form page text. Important statements inside `Answer` sections are not
always represented as evidence-backed claims, entities, or relations before page
generation.

This weakens long-term wiki maintenance:

- new sources cannot reliably strengthen, revise, or contradict prior claims;
- lint can inspect page structure but has limited access to knowledge-level
  evidence;
- query and chat can retrieve pages, but cannot always explain which source
  evidence supports a specific answer statement;
- ingest reports show written pages more clearly than extracted knowledge.

## Goals

- Add a lightweight knowledge atom layer between source digest and page draft.
- Keep Markdown wiki pages as the primary human and AI reading surface.
- Treat Markdown wiki pages as readable projections of knowledge atoms, not as
  the durable knowledge boundary.
- Represent only durable, reusable knowledge atoms, not every sentence.
- Require provenance for claims, relations, and evidence spans.
- Separate source-level digesting, atom extraction, page planning, page
  drafting, and indexing responsibilities.
- Keep the design compatible with the machine index, lint governance, query,
  chat, and report layers.
- Align page planning with the unified page namespace decision: physical
  directories are migration details, while page type is represented by
  metadata, virtual facets, and atom indexes.

## Non-Goals

- Do not turn KnoArbor into an RDF, SPARQL, ontology, or graph database
  project.
- Do not make triples the primary user-facing artifact.
- Do not run full named-entity recognition on every source.
- Do not force every page paragraph to become an atom.
- Do not treat source digests as concept pages unless the user is asking about
  the source itself.
- Do not expand short excerpts, quotes, or one-line insights into article-length
  synthesis when the evidence only supports a small claim or micro page.
- Do not make old `Answer` prose the long-term knowledge boundary; new page
  rendering should expose auditable claims and typed relations while preserving
  readable synthesis.
- Do not expose atom-level controls in the default user workflow.
- Do not make `concepts/`, `entities/`, `workflows/`, `comparisons/`,
  `queries/`, or `timelines/` the long-term canonical page type boundary.

## User Scenarios

### Source Compiles Into Evidence-Backed Wiki

When a user ingests a technical note, KnoArbor should extract source-level
observations, durable claims, entities, and relations before drafting pages. The
final page should remain readable, while the report should show the extracted
atom counts and unsupported atom rejections.

### New Source Updates Existing Knowledge

When a new source repeats or refines an existing conclusion, KnoArbor should
link the new evidence to the existing page or claim instead of creating a
duplicate page.

### Source Contradicts Existing Knowledge

When a new source conflicts with an existing claim, KnoArbor should preserve
both sides as evidence-backed claims or a contradiction signal. It should not
silently overwrite the prior conclusion.

### Query Needs Traceable Answers

When chat answers from a wiki page, the page should be traceable to source
digests and knowledge atoms, so citations can represent evidence rather than
only page-level proximity.

### Short Excerpt Compiles Without Overexpansion

When a user selects a sentence, quote, or short answer from Chat and compiles it,
KnoArbor should either attach it as an evidence-backed claim to an existing page
or create a compact micro page. It should preserve the original excerpt and avoid
inventing a broad article from thin evidence.

## Acceptance Criteria

- A `knowledge_atoms.v2` schema exists for entities, claims, relations, and
  evidence spans.
- Claims require direct evidence.
- Relations require either direct evidence or source claim references.
- Ingest design documents define the pipeline boundary:

  ```text
  raw -> source digest -> knowledge atoms -> page plan -> page draft -> indexes/reports
  ```

- Existing ingest behavior can continue while the atom layer is introduced.
- Future tasks identify how reports, indexes, page drafts, lint, query, and chat
  consume atom data.
- New Wiki pages expose `Summary`, `Claims`, `Entities`, `Relations`,
  `Evidence`, and `Synthesis` sections.
- Page planning, draft compilation, draft review, and the deterministic quality
  gate share the same source digest and atom trace contract.
- Approved writes are rejected before persistence when the page plan or draft
  lacks source digest trace, or when a non-source page lacks selected atom
  trace.
- `Synthesis` is treated as a derived reading layer. Major factual statements in
  synthesis must map back to selected atoms or direct source evidence.
- Typed relations and Markdown wikilinks are separate concepts. Relations carry
  type, direction, support, confidence, and status; wikilinks remain the reading
  navigation surface.
- Short-text ingest can produce claim updates, candidate pages, micro pages, or
  quote/source views without forcing full-length page generation.
- Page plans can emit canonical page identity metadata, including
  `canonical_path`, `legacy_paths`, `page_kind`, `subject_kind`, and `facets`.
- New page/index design treats `sources/` as the source digest/provenance
  boundary and treats concept/entity/workflow/comparison semantics as virtual
  facets rather than required physical directories.
