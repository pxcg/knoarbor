# 1.13 Knowledge Atom Ingest Design

## Design Summary

KnoArbor ingest becomes a knowledge compiler rather than a page generator. The
pipeline still writes Markdown wiki pages, but page drafts are downstream of
source digests and evidence-backed knowledge atoms.

The frozen design principle is:

> Ingest produces evidence-backed knowledge atoms. Markdown wiki pages are
> readable projections of those atoms, not the durable fact boundary.

This keeps KnoArbor distinct from a polished summarizer and from chunk-oriented
RAG. A page is a stable knowledge-object view composed from identity, scope,
claims, typed relations, evidence, and readable synthesis.

```text
Connector / Document Processor
  -> SourceDocument
  -> Checkpoint Window
  -> Source Segmentation
  -> Source Digest
  -> Knowledge Atom Extract
  -> Atom Validate / Deduplicate / Link
  -> Page Plan
  -> Page Draft Compile
  -> Page Review
  -> Write Pages
  -> Update Atom Index + Page Index + Reports
```

## Layer Ownership

### Raw Source Layer

Owner: connectors, document processing, source pipeline, segmentation.

Responsibilities:

- preserve source identity, path, hash, connector, and segment metadata;
- run parsing, redaction, and segmentation;
- provide stable source units for evidence references.

This layer does not interpret source meaning.

### Source Digest Layer

Owner: semantic source normalization and source digest extraction.

Responsibilities:

- summarize one source or source segment;
- list source-level observations and limitations;
- preserve mentioned entities and source focus;
- provide evidence spans that downstream atoms can cite.

Source digest Markdown is a view. It is not the only storage shape.

### Knowledge Atom Layer

Owner: semantic atom extraction, atom validation, atom index.

Responsibilities:

- extract durable facts, claims, and relations;
- require provenance for machine-usable knowledge;
- reject unsupported facts and claims before page drafting;
- deduplicate equivalent atoms across sources;
- emit contradiction and orphan signals for lint/report layers.

Atom types:

- `Fact`: low-dispute source-backed statement.
- `Claim`: interpretive, evaluative, causal, recommendation, decision, or open
  question statement.
- `Relation`: typed link between pages, entities, claims, concepts, sources, or
  workflows.

The atom layer is not an RDF store. It uses a small relation vocabulary and can
be stored as JSONL or rebuilt into a later SQLite provider.

### Page Plan Layer

Owner: ingest page planning.

Responsibilities:

- decide which atoms belong to which page;
- choose create/update/skip operations;
- map atom sets to page types;
- assign page identity metadata, such as `page_kind`, `subject_kind`,
  `facets`, `canonical_path`, and `legacy_paths`;
- choose related pages and relation reasons;
- expose rejected page candidates.

The current `WikiRelationPlan` behaves like a page write plan. The new design
will either rename it to `WikiPagePlan` or introduce `WikiPagePlan` beside it
before deprecating relation-plan wording.

Page planning follows [ADR 0002](../../docs/adr/0002-unified-page-namespace.md):
physical directories are not the canonical knowledge type boundary. The
long-term target is a unified `pages/` namespace for knowledge pages, with
`sources/` reserved for source digest and provenance views. Concept, entity,
workflow, comparison, claim, and relation semantics are represented by metadata,
page sections, atom indexes, and virtual facets.

### Page Draft Layer

Owner: page draft compiler and review.

Responsibilities:

- compile readable Markdown pages from selected atoms and existing page
  context;
- expose `Definition`, `Claims`, `Relations`, and `Synthesis` as the canonical
  user-facing page body;
- keep legacy `answer` as a schema compatibility input that maps to
  `Synthesis`, not as the primary knowledge boundary;
- attach source digest ids and atom ids in frontmatter or report metadata;
- reject page statements that cannot be linked to source evidence or approved
  atoms.

Canonical page sections:

- `Summary`: short page-level abstract for scanning, cards, and quick query
  previews.
- `Scope`: the page subject boundary, including what the page covers, excludes,
  or treats as version/time scoped.
- `Source Focus`: the source topic, question, or context this page was compiled
  from. Source focus is provenance context, not the page subject boundary.
- `Definition`: stable identity or definition for the page subject.
- `Claims`: auditable statements backed by selected atoms or direct source
  evidence.
- `Relations`: typed page/object edges, such as `contrasts`, `depends_on`,
  `implemented_by`, or `supported_by`.
- `Synthesis`: readable prose that integrates definition, claims, and
  relations for human and host-AI reading.
- `Key Points`: compact reading and retrieval hints; useful for cards and
  skimming, but not the primary evidence boundary.
- `Related Pages`: navigation links for wiki browsing.
- `Tags`: lightweight categorization for filtering and retrieval.
- `Source`: source paths used to compile or update the page.

`Synthesis` is a derived reading layer. It may explain, connect, and organize
claims and relations, but it must not introduce unsupported facts that are
missing from the selected atoms or direct source evidence. If the synthesis were
removed, the page should still retain its knowledge skeleton through identity,
scope, claims, relations, and source evidence.

### Source Digest Boundary

Source digest pages describe what a raw source or source segment contributes.
They are audit and provenance views. They are not concept pages and should not
be treated as the primary answer object unless the user is asking about the
source itself.

Source digests answer:

- what the source says;
- which evidence spans were extracted;
- which facts, claims, or relations were proposed;
- which wiki pages were created or updated;
- which source material was rejected or left unresolved.

Knowledge pages answer:

- what is currently known about a stable subject;
- which claims support that subject;
- which typed relations connect the subject to other pages;
- which sources and evidence support the maintained view.

### Relation Boundary

Markdown wikilinks and typed relations coexist:

- wikilinks are the human reading and navigation surface;
- typed relations are the machine-usable semantic edge.

A wikilink only says that a page mentions another page. A typed relation says
how they are connected, such as `requires`, `depends_on`, `contrasts`,
`implements`, `supports`, `contradicts`, `example_of`, or `part_of`.

Page rendering may emit wikilinks from typed relations, but not every wikilink
must become a relation. Accepted relations require a relation type, direction,
target, support, confidence, and status.

### Short Text And Excerpt Boundary

Short selected text, quote-like material, and memorable one-line insights must
not be expanded into article-length pages by default. They can produce:

- a claim update on an existing page when the target subject is clear;
- a micro page when the excerpt itself is a stable knowledge object;
- a candidate page with open questions when evidence is too thin;
- a source digest or quote view when the content is primarily provenance.

Short sources should preserve their compactness. The semantic workflow should
prefer one or a few evidence-backed claims over broad synthesis, and reports
should make unsupported expansion visible.

### Index / Report Layer

Owner: machine index, reports, lint, query/chat presenters.

Responsibilities:

- store or rebuild page, source, fact, claim, relation, and evidence indexes;
- make atom counts and unsupported atom rejections visible in ingest reports;
- allow lint to detect unsupported claims, orphan atoms, contradictions, and
  stale page narratives;
- allow query/chat to prefer pages while retaining evidence traceability.

## Data Contracts

### Evidence Span

An evidence span points to the source unit or source digest material that
supports an atom. It contains a source digest id, optional source path/unit
coordinates, an excerpt, and optional char offsets.

### Fact

A fact contains:

- id;
- statement;
- optional structured subject/predicate/object;
- qualifiers;
- at least one evidence span;
- confidence.

### Claim

A claim contains:

- id;
- claim text;
- claim type;
- stance;
- supporting fact ids and/or direct evidence;
- scope and limitations;
- confidence.

### Relation

A relation contains:

- id;
- subject object;
- predicate from a small controlled vocabulary;
- target object;
- supporting fact ids, claim ids, or direct evidence;
- confidence.

## Storage

First-stage storage is file based and vault local:

```text
.knoarbor/index/knowledge_atoms.jsonl
```

The Markdown wiki remains the canonical user reading surface. Unified atom JSONL
is the machine-auditable layer. A later SQLite provider can replace JSONL when
query, lint, and report workloads justify it.

The target readable wiki layout is:

```text
wiki/
  pages/      # maintained knowledge pages
  sources/    # source digest and provenance pages
  _views/     # generated browsing views and virtual facets
```

During migration, legacy paths such as `concepts/<slug>.md` or
`entities/<slug>.md` may remain as aliases or existing pages. New schema and
index work should avoid treating those path prefixes as the durable page type
boundary.

## Prompt Boundary

Semantic agents may extract atoms and propose page plans. They must not own:

- storage;
- checkpoint commit;
- retries;
- report writing;
- lint policy;
- index rebuilds.

Validation and quality gates enforce the schema before writes.

## Rejected Alternatives

### Full RDF / Ontology Store

Rejected because KnoArbor sources include personal notes, chats, workflows,
recommendations, and project decisions. A strict ontology would add high
maintenance cost without matching the shape of most knowledge.

### Markdown-Only Claim Sections

Rejected as the only solution because it keeps machine-usable knowledge inside
page prose. Claim sections are useful views, but the atom layer must be
structured and independently indexable.

### Free-Form Page Draft Improvements Only

Rejected because better prompts can make pages more polished without making
knowledge more traceable or maintainable.
