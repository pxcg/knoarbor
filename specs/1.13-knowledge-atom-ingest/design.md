# 1.13 Knowledge Atom Ingest Design

## Design Summary

KnoArbor ingest becomes a knowledge compiler rather than a page generator. The
pipeline still writes Markdown wiki pages, but page drafts are downstream of
source digests and evidence-backed knowledge atoms.

The frozen design principle is:

> Ingest produces evidence-backed knowledge atoms. Markdown wiki pages are
> readable projections of those atoms, not the durable knowledge boundary.

This keeps KnoArbor distinct from a polished summarizer and from chunk-oriented
RAG. A page is a stable knowledge-object view composed from identity, summary,
claims, typed relations, entities, evidence, and readable synthesis.

```text
Connector / Document Processor
  -> SourceDocument
  -> Checkpoint Window
  -> Source Segmentation
  -> Deterministic Source Parse
  -> Source Digest
  -> Knowledge Atom Extract
  -> Atom Validate / Deduplicate / Link
  -> Graph + Text Candidate Retrieval
  -> Page Plan
  -> Deterministic Page Assembly
  -> Synthesis Generation
  -> Deterministic Write Gate
  -> Conditional Semantic Review
  -> Write Pages
  -> Update Atom Index + Page Index + Reports
```

The agent-level ownership boundary is frozen in
[Ingest Agent Boundary](agent-boundary.md). The design separates semantic
judgment from deterministic parsing, retrieval, page assembly, safety gates,
storage, and reports.

## Layer Ownership

### Raw Source Layer

Owner: connectors, document processing, source pipeline, segmentation.

Responsibilities:

- preserve source identity, path, hash, connector, and segment metadata;
- run parsing, redaction, and segmentation;
- provide stable source units for evidence references.

This layer does not interpret source meaning.

### Source Digest Layer

Owner: semantic source normalization and deterministic source digest projection.

Responsibilities:

- identify one source or source segment;
- preserve source focus and compact source summary;
- provide stable source units and evidence spans that downstream atoms can cite;
- expose the structured inputs needed by the source digest Markdown view:
  source identity, source summary, source units, contribution map placeholders,
  unresolved/rejected items, and raw source pointers.

Source digest Markdown is a view. It is not the only storage shape.

### Knowledge Atom Layer

Owner: semantic atom extraction, atom validation, atom index.

Responsibilities:

- extract durable entities, claims, relations, and evidence;
- require provenance for machine-usable knowledge;
- reject unsupported claims and relations before page drafting;
- deduplicate equivalent atoms across sources;
- emit contradiction and orphan signals for lint/report layers.

Atom types:

- `Entity`: named object or concept mentioned by claims.
- `Claim`: evidence-backed definition, assessment, comparison, recommendation,
  decision, causal statement, or open question.
- `Relation`: typed triple between entities, backed by source claims or direct
  evidence.
- `Evidence`: source span that supports claims or relations.

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
- carry selected claim or relation atom ids for non-source page
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

Candidate retrieval is owned by deterministic context providers. The target
direction is graph-first retrieval from atom objects, typed relations, source
lineage, and machine indexes, with text/BM25 retrieval as a supplemental
candidate path. The page planning agent receives lightweight candidate profiles
and chooses among them.

### Page Draft Layer

Owner: deterministic page assembly, synthesis generation, deterministic write
gate, and conditional semantic review.

Responsibilities:

- assemble readable Markdown pages from selected atoms and existing page
  context;
- expose `Summary`, `Claims`, `Entities`, `Relations`, `Evidence`, and
  `Synthesis` as the canonical user-facing body for ordinary knowledge pages;
- expose `Source Identity`, `Source Summary`, `Source Units`,
  `Contribution Map`, `Unresolved / Rejected`, and `Raw Source` as the
  canonical source digest audit body;
- keep legacy `answer` as a schema compatibility input that maps to
  `Synthesis`, not as the primary knowledge boundary;
- attach source digest ids and atom ids in frontmatter or report metadata;
- reject page statements that cannot be linked to source evidence or approved
  atoms.
- review high-risk drafts against the same page-plan evidence trace used by the
  assembly and synthesis layers;
- treat source trace, atom coverage, page identity, synthesis quality, and
  update safety as write gates before persistence.

The long-term page draft direction is:

```text
selected atoms + page operation
  -> deterministic PageAssemblyService
  -> synthesis-generation agent
  -> deterministic Markdown renderer
  -> deterministic IngestWriteGate
  -> conditional semantic review
```

This keeps page structure stable and uses semantic generation for summary,
synthesis, and complex update language rather than full page construction.

### Wiki Page Projection Contract

A wiki page is a Markdown projection of a structured knowledge object. It is not
the durable knowledge boundary. The durable boundary is the combination of page
identity, claims, evidence, relations, source digests, and atom traces.

The frozen page design uses one consistent page body shape for every maintained
wiki page:

- `Identity`: minimal metadata stored in frontmatter. The required identity
  fields are `created`, `updated`, and `content_hash`.
- `Summary`: short page-level abstract for scanning, cards, and quick query
  previews.
- `Claims`: the main content layer. Claims use stable identifiers such as `C1`,
  `C2`, and `C3`, and mark important objects with wiki links when useful.
- `Entities`: knowledge objects mentioned by claims or relation triples.
- `Relations`: claim-backed triples between entities, rendered as
  `Subject | Predicate | Object | Based on`.
- `Evidence`: source, range, basis, and confidence rows mapped to claim ids.
- `Synthesis`: readable prose derived from claims, relations, and evidence.

The page structure intentionally avoids directory-specific templates and
complex full/compact/micro profiles. Short material still uses the same
sections, but may contain only one claim, one evidence row, and a compact
synthesis.

`Synthesis` is a derived reading layer. It may explain, connect, and organize
claims and relations, but it must not introduce unsupported claims that are
missing from the selected atoms or direct source evidence. If the synthesis were
removed, the page should still retain its knowledge skeleton through identity,
claims, entities, relations, and evidence.

Section boundaries:

- `Summary` is routing and preview text, not a condensed version of every
  section.
- `Claims` are evidence-backed statements that can be updated, rejected,
  contradicted, or cited.
- `Entities` are mentioned objects, not a separate page taxonomy.
- `Evidence` links claims to source spans, source digests, or approved atoms. It
  is not a duplicate copy of all raw source text.
- `Relations` are typed semantic edges with direction, target, support,
  confidence, and status.
- Derived navigation such as related pages, tags, facets, or views belongs in
  machine indexes and frontend projections, not in the canonical Markdown page
  body.

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
- which source units anchor the extracted evidence;
- which accepted claim or relation ids contributed to downstream pages;
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
how they are connected, such as `requires`, `depends_on`, `contrasts_with`,
`implements`, `supports`, `contradicts`, `coordinates`, `includes`, or `part_of`.

Page rendering may emit wikilinks from typed relations, but not every wikilink
must become a relation. Accepted relations require a relation type, direction,
target, claim support, confidence, and status.

Atom object types identify generic knowledge objects. They do not encode the
old page-directory taxonomy. Page shape and page grouping are later planning
decisions; Stage 3 atoms only need objects, claims, relations, and evidence.

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
- Treating `Synthesis` or legacy `Answer` prose as the durable knowledge boundary.
  Readable prose remains a projection over claims, relations, and evidence.
- Treating source-side context as the page subject. Source context belongs in
  source digests and evidence mappings; page identity, claims, entities, and
  relations define the subject.
- Treating every wikilink as a typed relation. Wikilinks support reading;
  accepted relations require explicit type, direction, evidence, and status.
- Treating every related page as answer evidence. Related pages are navigation
  unless selected into the answer set by query/chat.
- Moving `Evidence` into inline prose only. Evidence remains a first-class page
  section so claim support can be audited and maintained independently from
  readable synthesis.

### Index / Report Layer

Owner: machine index, reports, lint, query/chat presenters.

Responsibilities:

- store or rebuild page, source, entity, claim, relation, and evidence indexes;
- make atom counts and unsupported atom rejections visible in ingest reports;
- allow lint to detect unsupported claims, orphan atoms, contradictions, and
  stale page narratives;
- allow query/chat to prefer pages while retaining evidence traceability.

## Data Contracts

### Evidence Span

An evidence span points to the source unit or source digest material that
supports an atom. It contains a source digest id, optional source path/unit
coordinates, an excerpt, and optional char offsets.

### Claim

A claim contains:

- id;
- claim text;
- claim type;
- stance;
- direct evidence spans;
- mentioned entity names;
- confidence.

### Relation

A relation contains:

- id;
- subject object;
- predicate from a small controlled vocabulary;
- target object;
- supporting claim ids or direct evidence;
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
