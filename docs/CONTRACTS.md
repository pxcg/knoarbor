# Contracts

This document is the entry point for KnoArbor's frozen contracts. It records the
stable boundaries that code, prompts, UI, API, tests, and documentation share.

Feature specs may explain why a design exists. This document states the current
runtime contract.

## Contract Layers

| Layer | Frozen contract | Owner |
| --- | --- | --- |
| Vault layout | `vaults/<id>/raw`, `wiki`, `maintenance`, `.knoarbor` | `storage.vault_layout` |
| Wiki page | `wiki/pages/*.md` frontmatter and body sections | `core.wiki_schema`, `semantic.wiki_render` |
| Source digest | `wiki/sources/*.md` audit sections | `core.schemas.source_digest`, `semantic.source_digest` |
| Raw attachments | `raw/assets/**` plus `raw/sidecars/**` metadata | `core.attachments`, document processors |
| Machine index | `.knoarbor/index/manifest.json`, `graph_index.json` | `storage.wiki_index`, `retrieval.graph_index` |
| Ingest flow | source input to checkpoint commit stage objects | `pipelines.ingest*`, `semantic.*` |
| Query flow | graph-first recall, BM25 rerank, answer-set response | `pipelines.query`, `retrieval.*` |
| Chat flow | tool trace, evidence pack, answer, citation resolver | `services.chat_*` |
| Reports and ledgers | human reports, machine ledgers, failure artifacts, token ledger | `audit.*`, `storage.ledger` |
| Public API | method-aware stable local HTTP API | `entrypoints.api_contract`, `docs/API_COMPATIBILITY.md` |
| UI contract | display surfaces and UI-only adapters | `docs/UI_CONTRACT.md`, `web/src` |

## Vault Layout

The supported runtime layout is:

```text
vaults/<id>/
  raw/
    inbox/
      documents/
      media/
      notes/
    normalized/
      chats/
      excerpts/
      markdown/
    assets/
      images/
      media/
      pages/
      tables/
    sidecars/
      documents/
      sources/
  wiki/
    pages/
    sources/
  maintenance/
    reports/
      ingest/
      lint/
      query/
      run-failure/
    archives/
  .knoarbor/
    index/
    ledgers/
    checkpoints/
    runs/
    queue/
    locks/
    logs/
    chat/
      sessions/
```

`raw/` stores source-faithful material and parsed assets. `wiki/` stores
human-facing Markdown knowledge and source audit pages. `maintenance/` stores
human-readable workflow reports. `.knoarbor/` stores machine runtime state.

## Wiki Page Contract

Knowledge pages live in `wiki/pages/*.md`.

Frontmatter fields:

- `created`
- `updated`
- `content_hash`

Body sections:

```md
## Summary
## Claims
## Entities
## Relations
## Evidence
## Synthesis
## Attachments
```

Section meanings:

- `Summary`: compact human preview of the maintained page.
- `Claims`: numbered maintained statements, using `C1`, `C2`, and so on.
- `Entities`: knowledge objects mentioned by the page.
- `Relations`: claim-backed triples with `Subject | Predicate | Object | Based on`.
- `Evidence`: claim-level support with `Claim | Source | Range | Basis | Confidence`.
- `Synthesis`: readable integration derived from claims, relations, and evidence.
- `Attachments`: readable rich-asset references with `Topic | Description`.

Claims are the center of the page. Entities, relations, evidence, synthesis,
and attachments exist to explain, connect, support, and present the claims.

## Source Digest Contract

Source digests live in `wiki/sources/*.md`.

Body sections:

```md
## Source Identity
## Audit Summary
## Source Units
## Contribution Map
## Unresolved / Rejected
## Attachments
## Raw Source
```

Section meanings:

- `Source Identity`: connector, raw pointer, digest ids, atom ids, and content hash.
- `Audit Summary`: processing facts for this source or source segment.
- `Source Units`: stable evidence units derived from source unitization.
- `Contribution Map`: accepted or pending source contributions and target pages.
- `Unresolved / Rejected`: warnings, rejected material, and unresolved material.
- `Attachments`: readable audit projection of source attachments.
- `Raw Source`: pointer back to raw material and content hash.

Source digests are source-oriented audit pages. They record what a raw source
contributed to maintained wiki pages.

Attachment table:

```md
| Attachment | Type | Topic | Description | Source Range | Status |
```

Visible source digest attachment rows are compact audit pointers. Asset paths,
hashes, MIME types, parser metadata, OCR/VLM raw output, coordinates, and
binary data live in raw sidecars and assets.

## Raw Attachment Contract

Raw assets live under `raw/assets/**`.

Attachment sidecars use `knoarbor.attachments.v1`:

```json
{
  "schema_version": "knoarbor.attachments.v1",
  "source": "raw/normalized/markdown/example.md",
  "attachments": [
    {
      "attachment_type": "image",
      "name": "figure.jpg",
      "description": "Figure caption or model-produced summary.",
      "relative_path": "raw/assets/images/figure.jpg",
      "mime_type": "image/jpeg",
      "content_hash": "sha256...",
      "metadata": {
        "page_idx": 0,
        "bbox": [0, 0, 100, 100],
        "parser": "mineru"
      }
    }
  ]
}
```

Sidecars preserve parser-specific detail. Wiki pages and source digests render
readable projections of that data.

## Machine Index Contract

The frozen machine index files are:

```text
.knoarbor/index/
  manifest.json
  graph_index.json
```

`manifest.json` records index state:

- `schema_version`
- `generated_at`
- `vault_path`
- `wiki_hash`
- `graph_index_hash`
- `page_count`
- `source_count`
- `node_count`
- `edge_count`

`graph_index.json` locates what to read:

- `nodes[]`: knowledge objects with `id`, `pages`, `aliases`, and `summary`.
- `edges[]`: claim-backed triples with `source`, `predicate`, `target`, `page`, and `claim`.
- `sources[]`: source digest to raw and page contribution mappings.

Additional index files such as `pages.json`, `links.json`, `sources.json`, and
`search.json` are internal derived caches. They can be rebuilt from the wiki and
are not the public index contract.

## Ingest Flow Contract

The ingest flow is:

```text
Source Input
  -> Source Segmentation
  -> Segment-level Semantic Extraction
  -> Source-level Aggregation
  -> Candidate Retrieval / Page Planning
  -> Draft Assembly
  -> Review / Write Gate
  -> Write / Index / Scoped Lint
  -> Report / Checkpoint Commit
```

Key stage objects:

- `SourceDocument`
- `SourceSegmentBatch`
- `KnowledgeExtract`
- `SourceDigest`
- `KnowledgeAtomBatch`
- `WikiPagePlan`
- `WikiDraftBatch`
- `IngestDraftReview`
- `VaultWriteResult`
- ingest report and checkpoint commit metadata

Stable observation steps:

```text
input
segment
normalize_agent
atom_agent
retrieval
plan_agent
draft_agent
review_agent
write_gate
write
```

Stable observation event types:

- `ingest_step_started`
- `ingest_step_finished`
- `ingest_step_skipped`

These observation names are runtime contract names. UI labels, translated copy,
and report prose are presentation details derived from these names.

## Query Flow Contract

Query is model-free. It returns selected wiki evidence, not a final natural
language answer.

Retrieval shape:

```text
query
  -> graph/index recall
  -> BM25 rerank inside candidates
  -> primary/supporting/source page selection
  -> context package
```

Graph index locates pages. Markdown pages explain.

Response schema:

- `schema_version`: `wiki_query.v1`
- `results`: ranked retrieval candidates returned to the caller.
- `primary_pages`: answer-bearing maintained pages.
- `supporting_pages`: maintained pages that add complementary evidence.
- `source_pages`: source digest pages used for provenance.
- `answer_scope`: deterministic description of the query breadth and vault scope.
- `answer_set`: stable page-role plan for answer construction.
- `evidence_coverage`: deterministic coverage signal for gaps and confidence.
- `context_pack`: model-facing text package for callers that need a prompt-ready
  evidence block.

`results` may include candidates outside the final answer set. `answer_set`
records which pages shape the answer. `source_pages` support provenance and
source-focused questions.

## Chat Flow Contract

Chat is the answer layer:

```text
user message
  -> tool plan
  -> query/read/reuse tools
  -> evidence pack
  -> answer model
  -> reference resolver
  -> rendered answer and citations
```

The evidence pack is the answer model's factual input. Public citations are
resolved from tool trace and evidence pack records, then normalized for display.

Evidence pack schema:

- `schema_version`: `chat_evidence_pack.v1`
- `primary_pages`
- `supporting_pages`
- `source_pages`
- `citation_pages`
- `further_results`
- `answer_scope`
- `answer_set`
- `evidence_coverage`

`citation_pages` is the model-visible reference order. `further_results` is
navigation material. The reference resolver produces the public citation list:

- explicit inline references such as `[1]` select pages from `citation_pages`;
- sparse references are renumbered for display;
- navigation-only `list_wiki_pages` results stay out of public citations unless
  the answer explicitly references them;
- `hidden_evidence_count` records evidence pages that were observed but not
  displayed as public citations.

## Report And Ledger Contract

Reports and ledgers are recorded in [`REPORT_CONTRACT.md`](REPORT_CONTRACT.md).

The short boundary is:

- `maintenance/reports/**` stores human-readable Markdown reports.
- `.knoarbor/ledgers/**` stores append-only machine records.
- `.knoarbor/runs/**`, `queue/**`, `locks/**`, and `logs/**` store runtime
  lifecycle state.
- token analysis is derived from `token_ledger.v1` records and historical flow
  ledgers.

Failure artifacts use `run_failure_record.v1` and keep flow, stage, request
summary, error code, retryability, and hint together.

## Public API Contract

Public API stability is recorded in `docs/API_COMPATIBILITY.md` and the
machine-readable contract in `src/knoarbor/entrypoints/api_contract.py`.

The public API contract is method-aware: method, path, request shape, response
shape, and error envelope belong together.

`/ui/api/*` routes are UI adapters for the bundled console and desktop shell.
They share internal schemas with the UI but are not external integration APIs.

## UI Contract

The UI contract is recorded in `docs/UI_CONTRACT.md`.

Public product surfaces:

- Chat: conversation, selected vault scope, evidence-backed answers, citations.
- Flows: run status, ingest, lint, query, reports, token analysis.
- Knowledge: maintained pages and graph views.
- Docs: project documentation.
- Settings: vaults, inputs, preprocessing, models, runtime, diagnostics.
