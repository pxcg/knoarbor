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
  -> Segment Source Normalize Agent
  -> Source Digest Audit
  -> Segment Wiki Atom Extract Agent
  -> Deterministic Source-level Atom Aggregation
  -> Atom Validate / Deduplicate / Closure
  -> Graph + Text Candidate Retrieval
  -> Wiki Page Plan Agent
  -> Deterministic Page Assembly
  -> Deterministic Write Gate
  -> Conditional Semantic Review Agent
  -> Write Pages
  -> Update Graph Index + Manifest + Atom Index + Reports
```

## Claims-First Page Invariant

For non-source wiki pages, selected claims are the page spine. A page operation
must select claim atom ids before it can select relation atom ids. Relation
atoms, entity lists, evidence rows, summaries, and synthesis are projections
around those selected claims:

```text
selected claim atoms
  -> page claims
  -> entities + relation triples + evidence rows
  -> summary + synthesis
```

This keeps page identity auditable. A relation-only operation can describe a
graph edge, but it cannot create or update a non-source page unless the claims
supporting that edge are selected for the same operation.

## Source Input Boundary

The first ingest boundary is deterministic and source-specific:

```text
Connector / Document Processor
  -> SourceRef
  -> RawSource
  -> SourceDocument
  -> Checkpoint Window
  -> Source Segmentation
```

Responsibilities:

- connectors discover source references, fetch immutable raw metadata, and
  normalize source-specific records into `SourceDocument`;
- document processors convert rich files such as PDFs or Office documents into
  Markdown before the shared connector path;
- checkpointing selects the source/window to process without interpreting
  source meaning;
- segmentation splits a normalized `SourceDocument` by source structure:
  headings for Markdown, turn groups for chat transcripts, sections/pages for
  parsed documents, and paragraphs for plain text.

Boundaries:

- this layer may parse source formats, normalize roles, remove empty or
  process-only records, and preserve source ranges;
- this layer does not decide page identity, page type, claim importance,
  relation meaning, create/update/skip actions, or wiki write policy;
- hard splitting is a last-resort budget operation and must remain visible in
  segment warnings.

### Frozen Source Input Contract

Source input is frozen as the ingest identity and windowing boundary. It answers
three questions before any semantic processing starts:

1. which source was discovered;
2. what immutable raw state and parser identity produced the normalized
   document;
3. which source window should enter the current ingest run.

The stable source contracts are:

- `SourceRef`: discovery reference. `source_id` is the stable connector-level
  logical identity, `connector` names the adapter, `source_type` names the
  source family, `uri` is the connector-addressable location, and
  `display_name` is a human label.
- `RawSource`: raw state. `raw_path` is the local raw or normalized raw path,
  `content_hash` identifies raw content bytes, `content_type` identifies the
  raw media type, and parser metadata records how the raw state was read.
- `SourceDocument`: normalized document contract for segmentation and semantic
  extraction. `origin.uri` preserves the connector location,
  `origin.raw_path` preserves the raw path, and `origin.original_path`
  preserves the user-facing original path when preprocessing created an
  intermediate Markdown file.
- `SourceFingerprint`: processing identity. `content_hash`,
  `connector_version`, and `parser_version` together define whether a source
  can be safely skipped. A connector or parser version change re-enters the
  source/window even when raw content is unchanged.
- `SourceCheckpointWindow`: current ingest window. File-like sources use full
  windows; append-only sessions use `from_index` and `to_index` based on
  connector-normalized raw indexes.

Session raw indexes are source-position indexes, not semantic turn ids. They
must remain stable across normalization filters so checkpoint windows do not
shift when system/tool/process-only records are ignored. Chat connectors should
store the original record index as `raw_index` in normalized turns/messages.

`SourceContent.text` is the canonical normalized content payload.
`SourceContent.sections` is a structured companion used by segmentation when
available. Connectors may omit sections only when the segmenter can recover
structure from text; chat connectors should populate sections with the same
stable raw indexes used by checkpoint windows.

Document processors are not knowledge connectors. Rich documents are converted
to Markdown or text first, then enter the shared connector path as ordinary
source documents. Source input does not own page planning, claim importance,
relation meaning, Markdown rendering, or wiki write policy.

### Frozen Source Segmentation Contract

Source segmentation is frozen as the ingest budget and structure-preservation
boundary. It answers three questions after source input and before semantic
extraction:

1. whether the normalized source can be processed as one unit;
2. which source-native structure should define processing windows;
3. which segment metadata and warnings must travel with semantic extraction.

The stable segmentation contract is:

- short sources remain a single full-source segment with `mode: none`;
- Markdown sources split by heading blocks first, then paragraphs when heading
  structure is unavailable;
- chat sources split by complete turn groups and preserve connector-normalized
  `raw_index` ranges;
- parsed document sources split by provided sections or pages;
- plain text sources split by paragraphs;
- hard splitting is allowed only when a structural block exceeds
  `max_chars_per_segment`, and it must preserve content by emitting multiple
  bounded parts plus a visible `hard_split` warning;
- segment metadata uses sibling outline context only. It may expose segment
  titles, indexes, source ranges, previous/next titles, and a source-level
  outline, but it does not copy sibling segment bodies into the current segment;
- `max_segments_per_source` is a warning threshold, not permission to fold
  tail content into oversized segments or drop later segments.

Segmentation does not perform semantic extraction, claim selection, relation
interpretation, page planning, wiki writes, or checkpoint commits. It also does
not use raw text overlap; cross-segment continuity is handled by source-level
aggregation after segment-local semantic extraction.

## Long Source Aggregation Boundary

Segmentation is a budget and structure-preservation mechanism, not a wiki page
boundary. For segmented sources, the ingest chain keeps semantic extraction
local but defers page planning until the whole source has been reassembled as
source-level atoms:

```text
segment 0 -> normalize -> source digest -> atom extract
segment 1 -> normalize -> source digest -> atom extract
segment N -> normalize -> source digest -> atom extract
  -> deterministic aggregate knowledge extract + source digest + atom batch
  -> validate / deduplicate / closure
  -> one source-level page plan
  -> one source-level draft / review / write batch
```

Responsibilities:

- segment-level agents preserve local meaning, source ranges, claims, entities,
  relations, and evidence;
- deterministic aggregation remaps segment unit indexes, merges duplicate atom
  objects, merges entity aliases, deduplicates equivalent claims, merges claim
  evidence, deduplicates relation triples, merges relation support, and
  preserves warnings with segment provenance;
- page planning sees the aggregated source contract and decides page boundaries
  from the full source context;
- checkpoint commit remains source/window-level and advances only after the
  aggregated source write path succeeds.

Boundaries:

- segment-level extraction does not create pages, update pages, choose page
  paths, or commit checkpoints;
- source-level page planning does not read raw segment bodies after atom
  extraction;
- write policy should not compensate for duplicate segment-created pages,
  because segment-created pages should not exist.

Step 4 is fully deterministic. It answers the source-level aggregation
question: after each segment has produced source-local atoms, what is the one
auditable contract for the original source?

It owns:

- source-unit merge and segment provenance metadata;
- evidence unit remapping from segment indexes to source-level indexes;
- equivalent claim deduplication and evidence merge;
- relation triple deduplication after claim id remapping, including merged
  support claim ids and evidence spans;
- source-level `KnowledgeAtomQualityReport`;
- pending `SourceDigest.contribution_map` entries derived from claims.

It does not own:

- claim creation;
- page boundary choice;
- target page assignment for contributions;
- Markdown body assembly;
- checkpoint commit eligibility.

## Agent Decisions

## Token Ownership Boundary

This spec freezes the token-reduction direction for claims-first ingest. The
goal is not to shorten prompts by lossy truncation. The goal is to assign each
piece of work to the layer that can own it most reliably.

AI-owned semantic work:

- identify durable claims from source material;
- decide which entities are durable knowledge objects rather than incidental
  words;
- choose relation predicates and relation support claims;
- decide page boundaries and create/update/skip plans;
- write human-readable `summary`, `synthesis`, and update patch prose;
- review high-risk semantic writes when deterministic gates are insufficient.

Code-owned deterministic work:

- source identity, path, hash, timestamps, connector, segment range, and source
  unit ids;
- source digest structure, source units, raw pointers, evidence hashes, and
  contribution maps;
- claim numbering, relation table formatting, evidence table formatting,
  source digest ids, atom ids, canonical paths, legacy paths, page kind, facets,
  and machine indexes;
- deterministic review gates such as missing evidence, unsupported relation
  claim ids, absent source trace, malformed patches, unsafe target paths, and
  schema violations.

Source digest pages are audit artifacts. They answer how raw material entered
the wiki, what units were considered, what claims/pages it contributed to, and
what was unresolved. They must not compete with maintained knowledge pages as
answer-bearing summaries. A short audit summary may be generated by code from
source units, contribution counts, written pages, and warnings; it must not be
an AI-authored knowledge summary of the raw source.

The target ingest chain is:

```text
SourceDocument
  -> deterministic or lightweight semantic normalization
  -> semantic knowledge atom extraction
  -> deterministic atom normalization and validation
  -> page planning from atom profiles and candidate page profiles
  -> deterministic page assembly
  -> page-local prose generation
  -> deterministic review gates
  -> conditional semantic review for risky writes
  -> write / index / report
```

Implementation priority:

1. remove source digest page writing from page planning and draft compilation;
2. keep source digest audit pages code-generated from source units, selected
   atoms, write results, and warnings;
3. make draft compilation a page-local prose role that receives selected atoms
   and page assembly, not full source digests or broad source text;
4. run deterministic review before semantic review, and call semantic review
   only for update, conflict, duplicate-risk, weak-evidence, or gate-requested
   regeneration cases.

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
- preserve uncertainty and source-local confidence through claim stance,
  confidence, warnings, and evidence;
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

## Segment-level Semantic Extraction Substeps

Step 3 has four named substeps. The names describe operations; the input and
output names describe data contracts.

```text
3.1 Normalize Source Segment
    SourceDocument -> KnowledgeExtract

3.2 Build Source Digest
    KnowledgeExtract -> SourceDigest

3.3 Extract Knowledge Atoms
    SourceDigest -> KnowledgeAtomBatch

3.4 Validate Knowledge Atoms
    KnowledgeAtomBatch -> KnowledgeAtomQualityReport
```

Boundary rules:

- `Normalize Source Segment` preserves source units and removes process noise.
  It may use a model because mixed chat, notes, and tool output require
  semantic judgment.
- `Build Source Digest` is deterministic source audit projection. It owns the
  structured data for `Source Identity`, source audit summary, `Source Units`,
  raw source pointers, and source-level unresolved/warning items. It does not
  own final `Contribution Map` targets because page planning has not happened
  yet. The audit summary is code-generated from processing facts and must not
  become an AI-authored knowledge summary.
- `Extract Knowledge Atoms` is the only substep that creates claims. Entities,
  relations, and evidence are extracted around those claims rather than as
  independent page decisions.
- `Validate Knowledge Atoms` reports atom consistency issues without deciding
  wiki page writes. It is code-owned and produces `KnowledgeAtomQualityReport`
  for reports, gating, and later lint signals.

Step 3 output is source-local. It may be aggregated across segments in Step 4,
but it must not create pages, choose paths, write Markdown, or commit
checkpoints.

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
- every actionable operation must carry `source_digest_ids`;
- every non-source actionable operation must select claim atom ids; relation
  atom ids are auxiliary and cannot replace the selected claim spine.

### Page Draft Compile Agent

Status: retained only as a page-local prose-generation role; deterministic page
assembly owns the structural page body.

Question answered: how should selected atoms be expressed as readable wiki
language?

Semantic responsibilities:

- generate concise summaries from selected claims and synthesis;
- generate readable synthesis grounded in selected atoms and direct evidence;
- phrase update patch content when a planned update requires prose;
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
- source digest audit pages are not compiled by this agent;
- the agent does not choose page operations, page paths, or extra pages;
- the agent does not regenerate claims, entities, relations, evidence, source
  digest ids, atom ids, paths, or metadata;
- generated synthesis must be a reading layer over selected atoms.

Target implementation direction:

```text
selected atoms + page operation
  -> deterministic PageAssemblyService
  -> page-local prose payload
  -> summary / synthesis / update prose
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

The write path separates source/segment execution, semantic drafting, and
post-processing. The current implementation has these stable boundaries:

- `IngestSemanticRunner` owns the semantic ingest chain and returns a reviewed
  semantic result plus materialized page context.
- `IngestPostProcessor` owns approved draft commits, atom-index updates, and
  source-scoped deterministic lint.
- `ingest_checkpoint` owns checkpoint eligibility and commit payloads.

The target page-assembly path separates assembly, page-local prose generation,
the deterministic write gate, conditional semantic review, and persistence:

```text
Page Plan
  -> selected atom closure
  -> PageAssemblyService
  -> Page-local Prose Generation Agent
  -> MarkdownPageRenderer
  -> IngestWriteGate
  -> Conditional Semantic Review Agent
  -> Write
```

The write gate is deterministic and runs before persistence. It owns hard
checks over source trace, selected atom trace, write action eligibility, and
page-assembly projection. The semantic review agent owns meaning-level risk.
The remaining refactor is to make semantic review conditional and to report
deterministic gate decisions separately from semantic review decisions.

## Write / Report / Index Boundary

The final ingest boundary is deterministic. It receives approved operation
indexes and already-rendered draft content. It records write facts, refreshes
machine state, and emits user-visible audit artifacts:

```text
approved operation indexes + draft batch
  -> approved write items
  -> write policy
  -> WikiWritePipeline
  -> machine index refresh
  -> knowledge atom index upsert
  -> scoped deterministic lint
  -> checkpoint commit
  -> run report + ledgers
```

Responsibilities:

- persist approved create, update, and merge operations;
- canonicalize draft output before writing;
- record generated page paths immediately after page persistence;
- refresh generated views, page/search/link/source machine indexes, graph
  index, and manifest;
- upsert atom-to-page records for written pages;
- run scoped deterministic maintenance on touched pages when configured;
- commit checkpoints only after the write path produces a successful source
  result;
- write run reports, token ledgers, execution ledgers, and user-readable
  maintenance reports.

Boundaries:

- this stage does not call semantic agents;
- this stage does not create claims, entities, relations, evidence, page
  identities, or write decisions;
- this stage does not hide partial facts. If page persistence succeeds but a
  later index step fails, generated page paths remain part of the source result
  and reportable recovery context;
- checkpoint commit is source/window-level and belongs after write/index
  success, not inside page rendering or atom indexing.

## Selected Atom Closure Boundary

Selected atom closure is deterministic and claims-first. It answers one narrow
question: after a page operation selects claim atoms, which relations, entities,
evidence spans, and source digest traces must travel with those claims?

Responsibilities:

- keep selected claim ids as the page spine;
- include relation atoms whose `source_claim_ids` are fully covered by the
  selected claims;
- treat explicitly selected relation atoms as requests. Include them only when
  their supporting claims were selected by the same operation, otherwise report
  a closure issue;
- derive entity names from selected claim entity markers and selected relation
  subjects/objects;
- derive evidence keys from selected claim and relation evidence;
- carry selected source digest ids through to later draft and write gates;
- produce the selected atom batch consumed by compile and review agents.

Boundaries:

- closure does not choose page identity, write action, title, or path;
- closure does not invent claims, relations, entities, or evidence;
- closure does not repair unsupported atoms;
- closure reports unknown selected claim ids and relation ids as deterministic
  issues. The write gate blocks writes when such issues are present.
- closure does not validate source digest existence from atom evidence alone;
  that belongs to the source digest contract and write gate.

## Deferred Implementation

- Conditional semantic review triggers.
- Report fields that separate deterministic gate decisions from semantic review
  decisions.
