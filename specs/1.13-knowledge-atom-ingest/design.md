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
- carry `source_digest_ids` for every actionable operation;
- carry selected fact, claim, or relation atom ids for non-source page
  operations.

`WikiPagePlan` is the page write-planning contract. It selects page operations
from source digests and knowledge atoms, while typed relations remain
page-internal semantic edges rather than the name of the ingest planning stage.

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
- review each draft against the same page-plan evidence trace used by the draft
  compiler;
- treat source trace, atom coverage, page identity, synthesis quality, and
  update safety as write gates before persistence.

### Wiki Page Projection Contract

A wiki page is a Markdown projection of a structured knowledge object. It is not
the durable fact boundary. The durable boundary is the combination of page
identity, claims, evidence, relations, source digests, and atom traces.

The frozen page design separates three concerns:

- identity and routing metadata in frontmatter;
- auditable knowledge sections for claims, evidence, and relations;
- readable Markdown sections for human and host-AI consumption.

Recommended frontmatter fields:

- `schema_version`: page schema version, starting with `wiki_page.v1`;
- `page_profile`: `full`, `compact`, or `micro`;
- `role`: `knowledge_page`, `source_digest`, `generated_view`, or
  `micro_note`;
- `page_kind`: `concept`, `entity`, `workflow`, `comparison`, `timeline`,
  `query`, `note`, or `source_digest`;
- `subject_kind`: optional finer-grained subject classification;
- `facets`: virtual browsing and filtering categories;
- `aliases`: alternative names and legacy titles;
- `source_digest_ids`: source digest references used by the page;
- `atom_ids`, `claim_ids`, `relation_ids`: structured trace references;
- `canonical_path` and `legacy_paths`: stable page identity and migration
  aliases;
- `confidence`, `status`, `created`, and `updated`.

Canonical Markdown sections:

- `Summary`: short page-level abstract for scanning, cards, and quick query
  previews. It should identify what the page answers in one or two sentences.
- `Scope`: the page subject boundary, including what the page covers, excludes,
  or treats as version/time scoped.
- `Source Focus`: the source topic, question, or context this page was compiled
  from. Source focus is provenance context, not the page subject boundary. It is
  primarily useful on source digest pages or as collapsed provenance context.
- `Definition`: stable identity or definition for the page subject.
- `Claims`: auditable statements backed by selected atoms or direct source
  evidence.
- `Relations`: typed page/object edges, such as `contrasts`, `depends_on`,
  `implemented_by`, or `supported_by`.
- `Synthesis`: readable prose that integrates definition, claims, and
  relations for human and host-AI reading.
- `Key Points`: compact reading and retrieval hints; useful for cards and
  skimming, but not the primary evidence boundary.
- `Limitations / Open Questions`: evidence gaps, conflicts, weak claims,
  version caveats, or unresolved questions.
- `Related Pages`: navigation links for wiki browsing.
- `Tags`: lightweight categorization for filtering and retrieval.
- `Source`: source paths used to compile or update the page.

The sections are a projection contract, not a forced long-form template. Ingest
must choose the smallest page profile that preserves evidence and meaning:

#### Full Profile

Use `page_profile: full` for complex topics, multi-source synthesis, contested
material, or pages that define a reusable architecture or process.

Expected sections:

- `Summary`
- `Scope`
- `Definition`
- `Claims`
- `Evidence`
- `Relations`
- `Synthesis`
- `Key Points`
- `Limitations / Open Questions`
- `Related Pages`
- `Source`

#### Compact Profile

Use `page_profile: compact` for normal single-topic knowledge pages.

Expected sections:

- `Summary`
- `Definition` or `Core Idea`
- `Claims`
- `Relations` when explicit relations are supported;
- `Synthesis` when a readable integration is useful;
- `Related Pages`
- `Source`

Evidence may be inline inside `Claims` instead of a standalone section.

#### Micro Profile

Use `page_profile: micro` for short selected text, quote-like material, a single
chat insight, or thin evidence that should not be expanded into a full page.

Expected sections:

- `Summary`
- `Claim` or `Note`
- `Evidence`
- `Source`

Micro pages must preserve the compactness of the input. They should not invent
relations, broad background, or article-length synthesis from thin evidence.

`Synthesis` is a derived reading layer. It may explain, connect, and organize
claims and relations, but it must not introduce unsupported facts that are
missing from the selected atoms or direct source evidence. If the synthesis were
removed, the page should still retain its knowledge skeleton through identity,
scope, claims, relations, and source evidence.

Section boundaries:

- `Summary` is routing and preview text, not a condensed version of every
  section.
- `Definition` or `Core Idea` is the stable subject identity, not source
  provenance.
- `Claims` are evidence-backed statements that can be updated, rejected,
  contradicted, or cited.
- `Evidence` links claims to source spans, source digests, or approved atoms. It
  is not a duplicate copy of all raw source text.
- `Relations` are typed semantic edges with direction, target, support,
  confidence, and status.
- `Related Pages` are navigation links. They are not the same as typed
  relations.
- `Sources` are provenance references. They are not the same as evidence
  mappings.
- `Key Points` are quick reading and retrieval hints. They must not create a
  second, conflicting set of claims.

### Source Digest Boundary

Source digest pages describe what a raw source or source segment contributes.
They are audit and provenance views. They are not concept pages and should not
be treated as the primary answer object unless the user is asking about the
source itself.

The detailed source digest boundary is frozen in
[Source Digest Boundary](source-digest-boundary.md).

The schema storage and rule boundary is frozen in
[Schema Boundary](schema-boundary.md).

The graph-first machine index boundary is frozen in
[Index Boundary](index-boundary.md).

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

## Rejected Design Alternatives

- A fixed full-section Markdown template for every page. This makes short
  sources look complete when evidence is thin and encourages unsupported
  expansion.
- Treating `Synthesis` or legacy `Answer` prose as the durable fact boundary.
  Readable prose remains a projection over claims, relations, and evidence.
- Treating `Source Focus` as the page subject. Source focus is provenance
  context; `Scope`, `Definition`, and page identity define the subject.
- Treating every wikilink as a typed relation. Wikilinks support reading;
  accepted relations require explicit type, direction, evidence, and status.
- Treating every related page as answer evidence. Related pages are navigation
  unless selected into the answer set by query/chat.
- Requiring a standalone `Evidence` section on every page. Evidence is required
  semantically, but compact pages may inline evidence references inside claims.

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
