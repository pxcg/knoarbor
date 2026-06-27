# ADR 0001: Knowledge Atom Ingest

## Status

Accepted

## Context

KnoArbor ingests raw sources, chat records, notes, and prepared documents into a
local wiki. Early ingest flows can produce readable Markdown pages, but a
readable page is not enough to make the system distinct from a summarizer or
chunk-oriented RAG.

The durable design question is what a KnoArbor wiki page represents. If the
page is treated as the fact source, then claims, relations, evidence, and source
provenance remain embedded in prose. This makes long-term maintenance,
contradiction detection, source tracing, lint, and answer synthesis harder.

## Decision

KnoArbor ingest is a knowledge compilation pipeline:

```text
Raw Source
-> Source Record
-> Normalized Document
-> Evidence Spans
-> Knowledge Atoms
   -> Facts
   -> Claims
   -> Typed Relations
-> Reconciliation / Validation
-> Atom Index
-> Page Plan
-> Markdown Rendering
-> Lint / Report
```

Markdown wiki pages are readable projections of the atom and evidence layer.
They are the primary human and host-AI reading surface, but not the durable
knowledge boundary.

The accepted page model is:

- `Summary`: short scanning and routing summary.
- `Claims`: numbered auditable statements backed by atoms or direct evidence.
- `Relations`: claim-backed triples between entities.
- `Synthesis`: readable derived explanation based on claims and relations.
- `Entities`: important entities explicitly involved in claims and relations.
- `Evidence`: claim-to-source trace with source, range, basis, and confidence.
- `Attachments`: compact references to parsed figures or files when present.
- `Source`: source digests, raw source references, and evidence pointers.

`Synthesis` may remain because KnoArbor is a wiki, not a raw knowledge graph.
It is a derived reading layer and must not be treated as the only source of
truth. Major factual statements in synthesis should map to selected atoms or
direct source evidence.

Source digest pages are provenance and audit views. They describe what a raw
source or source segment contributed, which evidence was extracted, and which
wiki pages or atoms were affected. They are source audit pages rather than
maintained wiki knowledge pages.

Markdown wikilinks and typed relations coexist. Wikilinks are the reading and
navigation surface; typed relations are the machine-usable semantic edges with
direction, relation type, support, confidence, and status.

Short selected text, quotes, and one-line insights must not be expanded into
article-length pages by default. They can create claim updates, candidate pages,
micro pages, or source/quote views depending on the evidence available.

## Consequences

Positive consequences:

- Ingest can strengthen, revise, or contradict existing knowledge without
  relying on prose rewriting alone.
- Lint can validate source, evidence, atom, page, and graph consistency.
- Query and Chat can retrieve page objects while preserving evidence
  traceability.
- Short excerpts can be preserved as compact knowledge instead of overexpanded
  into speculative articles.
- Future storage can move from JSONL to SQLite or another provider without
  changing the conceptual boundary.

Costs:

- Ingest prompts and schemas must stay narrower and more structured.
- Reports need to explain atom counts, rejected atoms, unsupported claims, and
  page rendering decisions without overwhelming users.
- Page rendering must avoid drifting away from atom evidence.
- Relation vocabulary must stay small enough to maintain.

## Alternatives Considered

### Markdown Page As Fact Source

Rejected because claims, evidence, and relations remain embedded in free-form
text. This keeps the system close to an AI summarizer and makes maintenance
fragile.

### Pure Knowledge Graph

Rejected because KnoArbor must remain readable as a wiki. A strict graph or RDF
model would weaken the human reading surface and add ontology cost before the
project needs it.

### Better Page Draft Prompts Only

Rejected because better prose can make pages look more structured without
making knowledge more traceable, maintainable, or queryable.

### Chunk RAG Over Raw Sources

Rejected as the core model because it retrieves text proximity rather than
maintained knowledge objects. KnoArbor may use retrieval techniques internally,
but ingest output should be evidence-backed pages and atoms.

## Verification And Follow-Up

The owning spec is `specs/1.13-knowledge-atom-ingest/`.

Follow-up work should verify:

- knowledge atom schemas require evidence for machine-usable claims and
  relations;
- generated pages expose claims, relations, and synthesis as separate sections;
- synthesis does not introduce unsupported major factual statements;
- source digests remain provenance views and are separate from maintained wiki
  knowledge pages;
- short excerpt ingest creates compact knowledge artifacts or claim updates;
- lint can report unsupported claims, orphan atoms, contradictions, and stale
  page narratives;
- query/chat can use page-level answer sets while retaining atom and evidence
  traceability.
