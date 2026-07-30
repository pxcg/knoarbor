# 1.26 Raw-Grounded Ingest Chain Tasks

## Status

Accepted target contract. Public implementation and verification have not
started.

## Phase 1: Semantic Contract

- [ ] Introduce `ModelExtraction.v7`, remove relation `unit_positions`, and add
  exact claim evidence quotes.
- [ ] Align prompt, schema, semantic contract registration, fixtures, and fake
  provider payloads on the v7 field meanings.
- [ ] Add strict ownership tests proving the model schema contains no IDs,
  evidence objects, paths, attachments, or runtime fields.
- [ ] Preserve synthesis as retrieval-locator text in prompt and schema.

## Phase 2: Deterministic Compilation

- [ ] Compile directly into `KnowledgeAtomBatch.v3` with no model positions or
  duplicate intermediate payload.
- [ ] Validate each claim quote against the canonical evidence view, map it
  back to the Raw-unit range, and reject missing evidence without unit-wide
  fallback.
- [ ] Reject an invalid quote at the parent-claim boundary and rebuild relation
  support from accepted claims.
- [ ] Reject corrupt persisted evidence ranges without widening.
- [ ] Derive relation evidence exclusively from accepted supporting claims.
- [ ] Keep source contribution names and aliases separate from canonical entity
  snapshots through 1.27 linking.
- [ ] Make segment merge independent of segment numbering and completion order.
- [ ] Persist ambiguities and typed rejection details only as diagnostics.

## Phase 3: Fact Payloads

- [ ] Define versioned `source.json`, `knowledge.json`, `diagnostics.json`, and
  `manifest.json` schemas.
- [ ] Put source units and attachment metadata in `source.json`.
- [ ] Put synthesis, entities, claims, relations, and evidence in
  `knowledge.json`.
- [ ] Keep factual retrieval on the versioned knowledge payload rather than a
  second mutable representation.
- [ ] Coordinate the physical path and migration with 1.17 and publication with
  1.37.

## Phase 4: Projection

- [ ] Render selected source metadata and synthesis.
- [ ] Render every claim with evidence excerpt and stable source location.
- [ ] Render entity names and explicit aliases without unconditional Wiki links.
- [ ] Render relation triples with human supporting-claim labels.
- [ ] Render attachments with existing topic, description, and local thumbnail.
- [ ] Omit absent optional attachment fields without generated prose.
- [ ] Keep ambiguities, rejection details, provider data, and runtime state out
  of the ordinary body.

## Phase 5: Migration And Deletion

- [ ] Migrate active legacy fact generations without model calls.
- [ ] Verify old and new payload hashes and source-head equivalence.
- [ ] Delete legacy fact writers, readers, file names, and fallback branches.
- [ ] Rebuild projections and indexes from migrated facts.

## Closure

- [ ] Pass automated commands and artifact inspections in `verification.md`.
- [ ] Run a short and long real-model audit without retaining test artifacts.
- [ ] Update stable public architecture, contract, provenance, and backup docs.
- [ ] Mark the revision implemented only after the old fact path is absent from
  production readers and writers.

## Obsidian Local Image Extension

- [ ] Resolve standard and Obsidian local image syntax through the Markdown
  connector's configured source root with deterministic ambiguity rejection.
- [ ] Materialize validated local attachments into content-addressed
  `raw/derived/assets` paths before immutable input-generation serialization.
- [ ] Derive Raw display Markdown from persisted attachment mappings without
  rewriting Raw authority or ordinary Wiki-link semantics.
- [ ] Verify connector resolution, source-tree-independent asset retention,
  Raw rendering, unresolved embeds, and the affected documentation gates.

## Attachment Privacy Boundary Correction

- [ ] Preserve attachment machine identity across model-input redaction.
- [ ] Keep descriptive attachment text subject to the configured privacy rules.
- [ ] Cover hash-like filenames containing phone-shaped digit runs.

## Source-Language Fidelity

- [ ] Emit `mixed` for bilingual source material and provide a local language
  hint for every model-visible source unit.
- [ ] Require extracted semantic elements to follow their supporting source
  wording instead of one document-wide output language.
- [ ] Cover Chinese, English, and bilingual language hints in focused tests.
- [ ] Remove deterministic language-mismatch detection and publication
  rejection while retaining source-language fidelity in the extraction prompt.
- [ ] Remove relation-conflict, unused-entity, and missing-synthesis ingest
  diagnostics while retaining structural grounding checks.

## Compiler Validation Clean Path

- [ ] Reject an entity candidate when its primary source-written name is absent
  from its cited evidence.
- [ ] Consolidate deterministic source identity, atom identity, evidence, and
  reference-closure checks in the compiler.
- [ ] Delete the duplicate knowledge-atom quality subsystem, quality-gate
  payload, approved-segment list, aggregate rejection warning, and `rejected`
  lifecycle state.
- [ ] Keep dry-run and write execution on one candidate-outcome calculation.
