# 1.13 Knowledge Atom Ingest Tasks

## P0 Atom Contract

- [x] Create SDD requirements, design, tasks, and verification.
- [x] Add `knowledge_atoms.v1` schema for evidence, facts, claims, and
  relations.
- [x] Add unit tests for schema validation and atom summary counts.
- [x] Add atom contract exports to public internal schema package.

## P1 Source Digest Boundary

- [x] Split current source normalization output into source normalization and
  source digest concepts.
- [x] Add source digest structured fields for observations, limitations,
  mentioned entities, and evidence spans.
- [x] Add compatibility bridge from current `KnowledgeExtract` to
  `SourceDigest`.
- [x] Update source digest report payloads without changing existing page
  output.

## P2 Atom Extraction

- [x] Add `wiki_atom_extract_agent` prompt and semantic runner method.
- [x] Insert atom extraction after source digest and before page planning.
- [x] Add quality gate checks for unsupported facts, claims, and relations.
- [x] Add report fields for extracted fact, claim, relation, and evidence span
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
- [x] Update Markdown templates to expose Definition, Claims, Relations, and
  Synthesis instead of centering on legacy Answer prose.
- [x] Pass selected fact, claim, relation, and source digest ids through the
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
- [ ] Add deterministic claim/relation/evidence closure as a reusable service.
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
