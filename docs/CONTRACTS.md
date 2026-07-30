# Contracts

This document is the index of KnoArbor's stable cross-layer contracts. It
defines shared authority and data-flow boundaries. Detailed public HTTP, UI,
report, and provenance rules belong to their linked owner documents.

## Contract Owners

| Contract | Owner |
| --- | --- |
| Public HTTP compatibility | [API Compatibility](API_COMPATIBILITY.md) and [API Reference](API.md) |
| CLI behavior | [CLI Reference](CLI.md) |
| UI surfaces and adapters | [UI Contract](UI_CONTRACT.md) |
| Reports, ledgers, and failure artifacts | [Report Contract](REPORT_CONTRACT.md) |
| Source, evidence, and factual authority | [Provenance](PROVENANCE_DESIGN.md) and [ADR 0004](adr/0004-ingest-factual-authority.md) |
| Vault paths | `storage.vault_layout` and specification 1.17 |
| Ingest runtime | specification 1.37 |
| Ingest semantic chain | specifications 1.26 and 1.27 |
| Query retrieval and evidence resolution | specification 1.38 and ADR 0003 |

Feature specs explain implementation intent. This document and its linked
contract owners describe the current supported boundary.

## Vault Contract

The desktop product root contains `config.yaml`, `vaults/`, `state/`, `logs/`,
`cache/`, and `tmp/`. Its only runtime endpoint is `state/endpoint.json`;
top-level or home-directory `.knoarbor` runtime authorities are invalid.

```text
vault/
  raw/                    source-faithful inputs and deterministic derivatives
  wiki/pages/             authored pages and readable source projections
  artifacts/              user-visible generated files
  maintenance/reports/    human-readable workflow reports
  .knoarbor/
    ingest.sqlite         transactional ingest and active-head authority
    facts/                immutable four-file factual source revisions
    ingest_inputs/        immutable admitted workflow inputs
    index/                rebuildable machine-index generations
    ledgers/              append-only machine audit
    runs/                 run presentation and events
    locks/ logs/          local coordination and diagnostics
```

Paths are vault-relative in persisted and public payloads. Raw source material
is not overwritten by model workflows. Runtime vault content, local config, and
credentials are excluded from source control.

## Factual Authority

Published ingest facts are the active source/session heads in
`.knoarbor/ingest.sqlite` plus their reachable immutable generations under
`.knoarbor/facts/`.

A factual revision contains:

- a structured source processing record and stable source units;
- evidence-backed entities, claims, and relations;
- source/revision identities and integrity metadata;
- source-level synthesis used for semantic location.

`wiki/pages/*.md` projections and `.knoarbor/index/` are rebuildable views. They
do not become alternate factual authorities. Legacy `wiki/sources/*.md` pages
remain readable but are not required by current ingest.

## Evidence Contract

Raw evidence and source units are factual answer material. Each persisted
evidence span identifies its source record, revision, source unit, excerpt, and
integrity information. Model-local array positions are transient extraction
references and do not survive factual compilation.

Claim extraction returns a normalized claim together with the smallest
sufficient verbatim quote from each supporting source unit. Compilation
validates that every quote occurs in its source unit, maps it to the original
source substring, and computes its character range and integrity hash. Repeated
or overlapping quotes are valid; repeated text maps to its first source
occurrence. Missing quotes reject extraction, and evidence never widens to the
complete source unit. Persisted spans may deduplicate excerpt text and
deterministically hydrate it from that unit and character range.

Entities, claims, and relations carry evidence. Relations also reference their
supporting claim identities. Wiki pages and atom summaries may locate facts but
are not promoted to raw evidence.

## Page Contracts

Two page forms share `wiki/pages/`:

- authored/maintained pages use the claims-first sections defined by the Wiki
  schema and renderer;
- deterministic source projections carry `schema_version`, `projection_kind`,
  `not_fact_material`, and source/revision identities, with readable
  `Synthesis`, `Claims`, `Entities`, and `Relations` sections.

Page type is expressed by metadata and structure, not physical type
directories. Projection rendering is model-free and rebuildable.

## Attachment Contract

Source attachments and deterministic processor outputs live under
`raw/derived/assets/**`; their path, hash, MIME, coordinate, and parser metadata
live under `raw/derived/metadata/**` or structured source records. User-visible
chat artifacts live under `artifacts/chat/**` with manifests.

Public page and API references use validated vault-relative paths. Asset
serving is constrained to the selected vault and rejects traversal.

## Machine Index Contract

`.knoarbor/index/` contains versioned page, graph, source, link, and retrieval
views. A complete generation is verified before `CURRENT` is atomically
published. Readers use one generation snapshot. Deleting machine indexes does
not delete factual knowledge. The same verified retrieval SQLite contains the
lexical documents and canonical-entity relation adjacency; each published
relation edge must retain complete supporting-claim closure to active facts.
Derived locator storage keeps parent Raw rerank text once per evidence identity
and does not duplicate complete immutable semantic evidence. A Query batch
verifies one snapshot per selected vault and shares it across expressions and
active reads.

## Ingest Contract

```text
source request
  -> immutable input generation
  -> SourceDocument normalization
  -> source unitization and conditional segmentation
  -> schema-constrained semantic extraction
  -> deterministic validation, merge, and entity linking
  -> immutable factual revision and active-head commit
  -> deterministic Wiki and machine-index materialization
  -> report and ledger
```

The model generates semantic candidates. Code owns reference validation,
evidence, IDs, hashes, paths, linking, publication, projection, diagnostics,
and recovery.

Semantic metadata preserves source language at the content-unit boundary.
Chinese and English units in one source may produce Chinese and English
entities, claims, predicates, and locator topics together; a document-level
language hint never forces output-wide translation. This is an extraction
prompt requirement, not a deterministic ingest gate; publication does not use
script-ratio language detection to reject grounded metadata.

Factual commit and materialization health are separately observable. Semantic
recovery reuses the immutable command/input under a new attempt. Projection
rebuild reads committed facts and never calls a model.

## Raw Revision Edit Contract

A Raw edit never mutates the active factual revision in place. It creates a new
immutable source document with the same source identity and submits it through
the standard queued ingest coordinator. The normal model extraction, quality
gate, factual publication, projection, index, report, cancellation, and recovery
contracts therefore apply.

The request carries the revision that opened the editor. Publication rejects a
stale parent instead of replacing a newer active head. A successful ingest
creates fresh synthesis, claims, entities, relations, and evidence from the
revised Raw material; projection overrides from an older Raw revision are not
carried forward.

## Query Contract

Query is model-free:

```text
query -> immutable active Claim/Entity/Relation + Raw-window recall
      -> fusion -> active evidence resolution -> evidence reads
```

Claims and edges provide structured recall; Raw locator windows independently
recover extraction misses. Both channels resolve to complete active source
units through one evidence owner. Synthesis and projection pages are locator
metadata, not answer facts. `wiki_query.v4` returns typed QueryOutcome,
vault-scoped evidence handles, separate evidence reads, channel status, gaps,
warnings, stats, and trace.
Query itself remains model-free. Chat may supply a validated document/chapter
`region_id` and `group_id`; Query resolves the region to active source record
and source unit membership, then runs every expression through its ordinary
channels.
Region membership can filter that expression's candidates but cannot
manufacture a claim, candidate, citation, or relevance decision.
FTS5 match and field-weighted BM25 own lexical eligibility and channel order;
weighted reciprocal-rank fusion orders parent Raw identities. Query batch
retains the first 12 fused parents per region group, deduplicates them by
vault-scoped Raw identity, and retains the first 16 parents globally before
exact-span structural selection. These are retrieval result windows, not
confidence thresholds, context-character budgets, or user settings.
Literal and rewritten expressions are alternatives inside a group: a parent
keeps its best rank contribution rather than receiving additive votes for
matching both. Source images enter Chat only when the selected Raw unit
references them, and one attachment is emitted once per answer packet.
Relation atoms use the same atom/claim lexical channel and resolve through their batch-local `source_claim_ids`; Query exposes no graph traversal or relation-path response.

## Chat Contract

Chat reads one locator-only document/top-level-chapter outline derived from
active source processing and atom records. Each document node includes its
complete source-level synthesis so the optional dialogue-aware Retrieval
Planner can recognize a relevant document even when its headings use different
wording. The planner selects exact visible regions and writes one standalone
regional expression, then Chat sends it together with the unchanged question
in one shared region group through one Query-owned batch. Empty or unavailable
planning sends one unscoped unchanged query. Scope membership
cannot seed or authorize Raw. Apart from the document-level synthesis locator,
the outline contains no Raw, individual Claim/Entity/Relation row, attachment,
internal revision/evidence identity, or projection content and never becomes
factual material. Returned evidence separates
locator pages from `raw_evidence` and `source_unit` factual material.
Code enumerates exact active-Raw sentence and structural-line support spans.
Grounded synthesis selects their request-local IDs, and code owns the resulting
answer-bearing citation spans and order. Retrieval match spans and
`citation_pages` remain locator context. The reference resolver validates and
renumbers only these code-issued public citations. One public marker represents
one selected Raw source unit. Its locator keeps every exact selected range;
overlapping or touching ranges may collapse, while disjoint ranges remain
separate and are never widened into one enclosing range. Persisted Chat
citations remain locator-only. Preview resolves all answer-selected text on
demand from the cited immutable source unit and keeps that text transient.
Source-unit-local offsets never slice the complete Raw document, and an
unavailable locator cannot manufacture a highlight.

Chat prepares one complete evidence projection for Answer Decision. That model
receives reader-facing source labels, support text and IDs, call-local visual
references, source-authored image captions, processor-extracted visual
content, typed retrieval outcome, and advertised capabilities. Code keeps
filenames, durable attachment and revision identities, character offsets,
filesystem paths, retrieval scores, duplicate citation projections, and
attachment Markdown outside the model payload.

Answer Decision returns exactly `mode`, `spans`, `visuals`, `gap`, and
`generated_image_prompt`. `mode` is `raw`, `general`, or `gap`. Raw decisions contain
one or more current support-span IDs and optional source-visual references;
general and gap modes contain no Raw references. A Raw decision may include a
partial gap. A general decision may identify an unsupported remainder, and a
gap decision requires a concise gap. Image generation remains available in any
mode only for explicit create-new intent and provider capability. A non-null
prompt is both authorization and provider input; a separate Boolean is not
returned. Code validates support authorization, uniqueness, visual ownership,
mode invariants, explicit image intent, provider capability, and prompt safety,
then invokes the provider before composition.

Code persists successful generated output and maps it to request-local
generated-visual references. It reports `not_requested`, `failed`, or
`available` to Response Composer without exposing provider URLs, stored paths,
artifact identities, or image Markdown. Code also maps validated Raw selections
to request-local material IDs. Each
material contains one code-owned reader-facing source label, exact selected Raw
texts in source order, and selected visual semantics. Response Composer
receives the original question, substantive dialogue-only history with
code-rendered citations and images removed, the validated mode and gap, and the
generated-image result. It does not receive support IDs, unselected Raw or
images, Query metadata, provider URLs, paths, offsets, or durable identities.

Response Composer returns ordered text, source-visual, and successful
generated-visual items plus optional partial-gap Markdown. A text item may
use natural multi-block Markdown; its selected-material mapping applies to the
whole item. Every selected material must support at least one text item, every
selected source visual must appear exactly once after text using its owner
material, and every successful generated visual must appear exactly once at a
composer-selected position. Code rejects transport
identities and standalone citation-like markers in reader-facing prose without
rejecting ordinary code, syntax examples, formulas, index notation, or
technical paths. It expands
material IDs to retained support spans, injects adjacent public citation
markers for Raw mode, and renders stored source/generated-image Markdown at the validated
item positions. General output has no
local citations or source visuals. Gap output has no answer items. Mixed
authority is rejected.

Answer prose follows the latest user's language composition. Chinese, English,
and genuinely mixed requests may keep their respective form, while
source-written names, technical terms, code, formulas, and direct quotations
remain unchanged unless translation is explicitly requested.

Every Raw-grounded answer exposes source-image semantics only to Answer
Decision when a current Raw caption or extracted content exists. A selected
visual is mandatory input to Response Composer and must be placed exactly once
as a typed source-visual item in an owner-adjacent single or contiguous visual
group. Model-authored image Markdown is invalid. Unknown, repeated,
non-owner-adjacent, cross-Raw, unselected, and empty-semantic visuals do not
render.
Answer Decision may return a non-null `generated_image_prompt` only when the
latest user intent semantically and explicitly requests creation of a new
image. Code runs that request before Response Composer, which places every
successful generated visual. A source-image request does not authorize a
generated replacement. Generated images carry a code-owned visible label that
they are not knowledge-base evidence.
Raw-linked images without a source caption or extracted content remain stored
but absent from model semantic context and final Chat image output.

Chat does not receive arbitrary shell, browser, filesystem, or network tools
and does not write Wiki Markdown directly.

Answer Decision is the sole semantic owner of whether current Raw supports the
original request, stable general knowledge is appropriate, or local evidence
is missing. Candidate and trustworthy no-match outcomes both continue through
Answer Decision and Response Composer. Typed index, integrity, timeout,
cancellation, and resource failures remain code-owned terminals. Code derives
provenance from the validated decision and does not use a no-match gate or
local-evidence keyword router. Session mutations use stable
request/message/turn identities plus
compare-and-swap `session_revision`; selected ingest uses `turn_ids`, never
array positions.

## Operational Contracts

- Stable error codes and response envelopes are documented in
  [Error Codes](ERROR_CODES.md) and [API Compatibility](API_COMPATIBILITY.md).
- Stable report and ledger schemas are documented in
  [Report Contract](REPORT_CONTRACT.md).
- UI adapters display service decisions and do not recreate workflow policy;
  see [UI Contract](UI_CONTRACT.md).
- Ingest observation stages are `input`, `document_process`,
  `source_unitize`, `index_metadata_agent`, `index_metadata_validation`, `index_write`,
  `projection`, and `report`.
- Runtime events and diagnostics are operational audit, not knowledge facts.
