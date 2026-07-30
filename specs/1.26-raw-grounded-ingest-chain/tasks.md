# 1.26 Raw-Grounded Ingest Chain Tasks

## Status

Implementation, automated verification, and isolated real-provider audit are
complete.

## Phase 1: Semantic Contract

- [x] Introduce `ModelExtraction.v7`, remove relation `unit_positions`, and add
  exact claim evidence quotes.
- [x] Align prompt, schema, semantic contract registration, fixtures, and fake
  provider payloads on the v7 field meanings.
- [x] Add strict ownership tests proving the model schema contains no IDs,
  evidence objects, paths, attachments, or runtime fields.
- [x] Preserve synthesis as retrieval-locator text in prompt and schema.

## Phase 2: Deterministic Compilation

- [x] Compile directly into `KnowledgeAtomBatch.v3` with no model positions or
  duplicate intermediate payload.
- [x] Validate each claim quote against the canonical evidence view, map it
  back to the Raw-unit range, and reject missing evidence without unit-wide
  fallback.
- [x] Reject an invalid quote at the parent-claim boundary and rebuild relation
  support from accepted claims.
- [x] Reject corrupt persisted evidence ranges without widening.
- [x] Derive relation evidence exclusively from accepted supporting claims.
- [x] Keep source contribution names and aliases separate from canonical entity
  snapshots through 1.27 linking.
- [x] Make segment merge independent of segment numbering and completion order.
- [x] Persist ambiguities and typed rejection details only as diagnostics.

## Phase 3: Fact Payloads

- [x] Define versioned `source.json`, `knowledge.json`, `diagnostics.json`, and
  `manifest.json` schemas.
- [x] Put source units and attachment metadata in `source.json`.
- [x] Put synthesis, entities, claims, relations, and evidence in
  `knowledge.json`.
- [x] Keep factual retrieval on the versioned knowledge payload rather than a
  second mutable representation.
- [x] Coordinate the physical path and migration with 1.17 and publication with
  1.37.

## Phase 4: Projection

- [x] Render selected source metadata and synthesis.
- [x] Render every claim with evidence excerpt and stable source location.
- [x] Render entity names and explicit aliases without unconditional Wiki links.
- [x] Render relation triples with human supporting-claim labels.
- [x] Render attachments with existing topic, description, and local thumbnail.
- [x] Omit absent optional attachment fields without generated prose.
- [x] Keep ambiguities, rejection details, provider data, and runtime state out
  of the ordinary body.

## Phase 5: Migration And Deletion

- [x] Migrate active legacy fact generations without model calls.
- [x] Verify old and new payload hashes and source-head equivalence.
- [x] Delete legacy fact writers, readers, file names, and fallback branches.
- [x] Rebuild projections and indexes from migrated facts.

## Closure

- [x] Pass automated commands and artifact inspections in `verification.md`.
- [x] Run a short and long real-model audit without retaining test artifacts.
- [x] Update stable public architecture, contract, provenance, and backup docs.
- [x] Mark the revision implemented only after the old fact path is absent from
  production readers and writers.

## Obsidian Local Image Extension

- [x] Resolve standard and Obsidian local image syntax through the Markdown
  connector's configured source root with deterministic ambiguity rejection.
- [x] Materialize validated local attachments into content-addressed
  `raw/derived/assets` paths before immutable input-generation serialization.
- [x] Derive Raw display Markdown from persisted attachment mappings without
  rewriting Raw authority or ordinary Wiki-link semantics.
- [x] Verify connector resolution, source-tree-independent asset retention,
  Raw rendering, unresolved embeds, and the affected documentation gates.

## Attachment Privacy Boundary Correction

- [x] Preserve attachment machine identity across model-input redaction.
- [x] Keep descriptive attachment text subject to the configured privacy rules.
- [x] Cover hash-like filenames containing phone-shaped digit runs.

## Source-Language Fidelity

- [x] Emit `mixed` for bilingual source material and provide a local language
  hint for every model-visible source unit.
- [x] Require extracted semantic elements to follow their supporting source
  wording instead of one document-wide output language.
- [x] Cover Chinese, English, and bilingual language hints in focused tests.
- [x] Remove deterministic language-mismatch detection and publication
  rejection while retaining source-language fidelity in the extraction prompt.
- [x] Remove relation-conflict, unused-entity, and missing-synthesis ingest
  diagnostics while retaining structural grounding checks.

## Compiler Validation Clean Path

- [x] Reject an entity candidate when its primary source-written name is absent
  from its cited evidence.
- [x] Consolidate deterministic source identity, atom identity, evidence, and
  reference-closure checks in the compiler.
- [x] Delete the duplicate knowledge-atom quality subsystem, quality-gate
  payload, approved-segment list, aggregate rejection warning, and `rejected`
  lifecycle state.
- [x] Keep dry-run and write execution on one candidate-outcome calculation.
