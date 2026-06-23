# Ingest Agent Boundary

This document freezes the ingest semantic-agent boundary for the knowledge atom
ingest line. It applies first-principles ownership rules to each ingest agent:

- semantic agents handle meaning, ambiguity, judgment, and synthesis;
- deterministic services handle parsing, indexing, evidence closure, rendering,
  safety gates, storage, reports, and lifecycle;
- each agent answers one durable ingest question;
- downstream agents receive the smallest source-backed contract that preserves
  correctness.

## Ingest Questions

Ingest exists to answer four questions:

1. Which parts of the raw source are substantive knowledge material?
2. Which claims, entities, relations, and evidence can be reused later?
3. Which stable wiki page or source digest should receive those atoms?
4. Is the resulting write traceable, maintainable, connected, and safe?

The pipeline should keep those questions separated:

```text
Connector / Document Processor
  -> SourceDocument
  -> Checkpoint Window
  -> Source Segmentation
  -> Deterministic Source Parse
  -> Source Normalize Agent
  -> Source Digest
  -> Wiki Atom Extract Agent
  -> Atom Validate / Deduplicate / Closure
  -> Graph + Text Candidate Retrieval
  -> Wiki Page Plan Agent
  -> Deterministic Page Assembly
  -> Synthesis Generation Agent
  -> Deterministic Write Gate
  -> Conditional Semantic Review Agent
  -> Write Pages
  -> Update Graph Index + Manifest + Atom Index + Reports
```

## Agent Decisions

### Source Normalize Agent

Status: retained with a narrowed role.

Question answered: which source content is substantive enough to become ingest
material?

Semantic responsibilities:

- remove ambiguous process noise from chats and mixed records;
- preserve substantive user and assistant content;
- generate human-readable source titles when connector metadata is weak;
- keep segment-local meaning grounded when a long source is split;
- preserve short selected excerpts without inflating their meaning.

Deterministic responsibilities:

- parse Markdown headings, JSONL records, sqlite rows, and document metadata;
- preserve source id, path, hash, timestamps, connector, and segment metadata;
- filter explicit system messages, tool schemas, terminal logs, empty records,
  and known process-only records;
- compute source fingerprints and stable source unit ordering.

Boundary:

- the agent produces `knowledge_extract.v1`;
- it does not decide page identity, page type, write action, related pages, or
  final prose;
- Markdown-only and clean structured sources may use deterministic pre-normalize
  paths before the agent is called.

### Wiki Atom Extract Agent

Status: retained as the primary semantic ingest agent.

Question answered: which reusable knowledge atoms are present in this source?

Semantic responsibilities:

- extract durable claims such as definitions, assessments, decisions,
  recommendations, comparisons, causal statements, and open questions;
- extract typed relations between durable knowledge objects;
- identify important entities and concepts as atom objects;
- preserve uncertainty, scope limits, and source-local confidence;
- map atoms to evidence spans or supporting atom ids.

Deterministic responsibilities:

- validate evidence requirements for claims and relations;
- normalize ids, hashes, confidence ranges, and relation vocabulary;
- reject unsupported atoms before page planning;
- compute dependency closure between selected claims, relations, entities, and
  evidence spans;
- deduplicate equivalent atom ids within the source batch;
- emit quality signals for reports and lint.

Boundary:

- the agent produces `knowledge_atoms.v2`;
- it does not decide page write actions, page titles, page paths, or Markdown
  page prose;
- it extracts durable atoms rather than sentence-level exhaustive triples.

### Wiki Page Plan Agent

Status: retained with retrieval responsibility moved to deterministic context
providers.

Question answered: which stable wiki objects should receive the selected atoms?

Semantic responsibilities:

- choose page boundaries;
- decide create, update, or skip operations;
- choose the stable knowledge object and page identity;
- select the claim and relation ids for each page operation;
- decide whether a source supports one primary page or several independently
  reusable pages;
- choose between updating an existing candidate and creating a new page.

Deterministic responsibilities:

- build graph-first candidate pages from atom objects, relations, source
  lineage, and existing indexes;
- add text/BM25 candidates as a supplemental retrieval path;
- merge and rerank candidate pools;
- enforce operation legality, target-page provenance, selected atom id validity,
  source digest trace, canonical path rules, and skip semantics;
- materialize only selected target, related, and candidate pages after planning.

Boundary:

- the agent consumes a compact `source_digest.v1`, `knowledge_atoms.v2`, and
  lightweight candidate profiles;
- it does not read full candidate page bodies during planning;
- it does not invent candidates outside the deterministic candidate pool;
- it does not write page bodies or patches.

### Page Draft Compile Agent

Status: retained only as a synthesis-generation role; deterministic page
assembly owns the structural page body.

Question answered: how should selected atoms be expressed as readable wiki
language?

Semantic responsibilities:

- generate concise summaries;
- generate readable synthesis grounded in selected atoms and direct evidence;
- rewrite or merge claims only when readability requires it;
- phrase update patch content for existing pages when the update has already
  been planned;
- keep language aligned with the source domain and source language.

Deterministic responsibilities:

- assemble page skeletons from selected atoms;
- render frontmatter, identity fields, entities, relations, evidence mappings,
  source digest ids, atom ids, and Markdown section order;
- derive entities from atom subjects, objects, and claim markers;
- derive relation triples from selected relation atoms;
- derive evidence rows from claim, relation, and source digest evidence;
- preserve canonical paths, legacy paths, page kind, facets, and operation
  identity from the page plan.

Boundary:

- the agent receives only selected atoms plus page-plan compile context;
- full raw source text is omitted after atom extraction;
- the agent does not choose page operations, page paths, or extra pages;
- generated synthesis must be a reading layer over selected atoms.

Target implementation direction:

```text
selected atoms + page operation
  -> deterministic PageAssemblyService
  -> synthesis-generation payload
  -> synthesis text
  -> deterministic Markdown render
```

### Ingest Draft Review Agent

Status: retained as conditional semantic audit.

Question answered: is this write semantically safe and useful?

Semantic responsibilities:

- judge page boundary fit;
- judge whether synthesis introduces unsupported meaning;
- judge semantic duplication risk across candidate pages;
- judge update safety when a patch modifies an existing page;
- judge complex source support when evidence is weak, conflicting, or partial.

Deterministic responsibilities:

- check schema validity;
- check selected atom coverage;
- check source digest trace;
- check relation and evidence formatting;
- check patch operation safety and allowed sections;
- check target paths and write actions;
- reject writes that fail hard structural gates before semantic review.

Boundary:

- the review agent runs for high-risk creates, existing-page updates, weak
  evidence, conflict signals, duplicate-risk signals, or failed deterministic
  gates that request regeneration;
- low-risk creates with complete source trace, selected atom trace, valid
  evidence closure, and deterministic gate success may skip semantic review;
- the agent reviews prepared drafts and never creates new operations.

## Retrieval Boundary

Ingest retrieval should become graph-first:

```text
knowledge_atoms
  -> entity and relation lookup in graph_index.json
  -> source lineage lookup in manifest/index data
  -> candidate page profiles
  -> text/BM25 supplemental candidates
  -> merged candidate set
  -> page plan
```

Graph retrieval owns the first candidate set because LLM-Wiki pages are
structured knowledge objects with entities, claims, relations, sources, and
evidence. Text retrieval remains useful for lexical aliases, thin indexes, and
early vaults with weak graph coverage.

`WikiPagePlan` receives candidate profiles, not full page bodies. Full page
content is materialized after page planning for selected target, related, and
candidate pages.

## Write Boundary

The long-term write path should separate assembly, synthesis, gate, and review:

```text
Page Plan
  -> selected atom closure
  -> PageAssemblyService
  -> Synthesis Generation Agent
  -> MarkdownPageRenderer
  -> IngestWriteGate
  -> Conditional Semantic Review
  -> Write
```

The write gate is deterministic and runs before persistence. It owns hard
checks. The semantic review agent owns meaning-level risk. Reports should show
which layer accepted, rejected, or requested regeneration.

## Deferred Implementation

- Graph-first ingest candidate provider.
- Deterministic `PageAssemblyService`.
- Rename or narrow `wiki_draft_compile` toward synthesis generation.
- Deterministic `IngestWriteGate` before semantic review.
- Conditional semantic review triggers.
- Report fields that separate deterministic gate decisions from semantic review
  decisions.
