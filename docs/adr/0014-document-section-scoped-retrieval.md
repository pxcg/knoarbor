# ADR 0014: Document-Section-Scoped Retrieval

## Status

Partially Superseded by [ADR 0016](0016-direction-first-retrieval-planning.md)

## Context

The unchanged user question can be too broad for a large corpus, but sending
every Claim, Entity, Relation, or derived graph community to a navigation model
causes the locator prompt to grow with semantic atom volume. Generating
replacement search questions also creates a second retrieval authority and can
lose useful wording from the original question.

Most parsed documents already have usable document and chapter structure.
Ingest must not publish another navigation artifact or require reingest.

## Decision

Query derives a locator-only `active_corpus_outline.v1` from active source
processing records. It exposes document titles and top-level chapter headings
with opaque `region_id` values. A chapter region contains all source units
under that chapter, including lower-level sections. A document region contains
all of that document's source units.

Chat may make one dialogue-aware navigation model call. The model can select
only visible region IDs. For every selected region, Query runs the unchanged
user question through its existing Raw lexical, Claim, Entity, and Relation
channels while filtering candidates to the region's active source units.
Several selected regions are evaluated in one Query-owned batch. If navigation
is empty or unavailable, Chat sends one unscoped unchanged question.

Region membership is only a search boundary. It cannot admit evidence, become
a citation, or replace Query relevance decisions. Query resolves and
deduplicates all routes to active Raw; only admitted Raw and retained source
attachments reach the answer model. Ingest schemas, prompts, facts, and
materialization remain unchanged.

## Consequences

- Navigation input grows with documents and top-level chapters, not semantic
  atom or Raw volume.
- Claims, entities, relations, and Raw remain Query channels inside the selected
  region instead of becoming a second navigation graph.
- The original question is never rewritten or supplemented with generated
  search prose.
- Documents without usable headings remain searchable through their document
  region and through the unscoped fallback.
- One local factual Chat request normally uses one navigation call, one Query
  batch, and one answer call.

## Alternatives

- **Semantic communities as the first navigation index:** rejected because
  isolated or numerous semantic nodes recreate prompt growth and duplicate
  Query's existing semantic channels.
- **Generated query expansion:** rejected because it can suppress or distort
  the original question.
- **A model call per candidate:** rejected because latency and token cost grow
  with recall volume.
- **Persisting a new ingest tree:** rejected because active processing records
  already contain the required structure.

## Verification

- Six retained documents produce one compact document/chapter outline without
  Raw content or internal evidence identities.
- Selected chapter regions admit only source units in those regions.
- Multi-region questions run the same unchanged question in every selected
  region and deduplicate shared Raw identities.
- Empty, invalid, or unavailable navigation falls back to one unscoped query.
- Existing single-query, relation, Raw resolution, citation, and no-match
  contracts remain valid.

