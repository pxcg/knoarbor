# API Reference

KnoArbor exposes a small public alpha HTTP API for local UI, CLI helpers, external workflow tools, and AI-tool skills. The API is plain JSON over HTTP and can be called from Apifox, Postman, curl, Python, or any OpenAPI-compatible client.

Start the service:

```bash
uv run knoar serve
```

Base URL:

```text
http://127.0.0.1:8000
```

Interactive docs:

- UI: `GET /`
- Swagger/OpenAPI: `GET /docs`
- OpenAPI JSON: `GET /openapi.json`

## Compatibility Policy

The endpoints in this document are the v0.x public alpha API surface. Workflow paths and core semantics are intended to remain stable during the v0.x line, while response schemas may receive additive fields before a later stable release.

- Paths, HTTP methods, required request fields, and core response field meanings are treated as stable for the v0.x alpha line.
- Additive optional fields may be introduced in minor versions.
- If a public endpoint is deprecated, it will be kept for at least one minor release.
- `/ui/api/*` is reserved for the local management UI and is not a stable integration API.
- The machine-readable compatibility list lives in `src/knoarbor/entrypoints/api_contract.py`; API surface tests read that contract directly.

Stable public surface for v0.x:

| Area | Endpoint family | Stability |
| --- | --- | --- |
| Service status | `GET /health`, `GET /doctor` | Stable public diagnostics |
| Synchronous workflows | `POST /ingest/*`, `POST /lint/run`, `POST /query/search` | Stable public workflow API |
| Run queue | `POST /runs/*`, `GET /runs*`, `POST /runs/{run_id}/cancel`, `POST /runs/{run_id}/rerun-failed` | Stable public long-run API |
| Query feedback | `POST /query/feedback`, `GET /query/trends` | Stable public telemetry API |
| Wiki pages | `GET /wiki/pages`, `GET /wiki/page`, `GET /wiki/backlinks` | Stable public page read API |
| Management UI | `GET /`, `GET /ui`, `/ui/api/*` | UI is public; `/ui/api/*` is internal |

## Error Contract

Public API errors use the shared KnoArbor error catalog. The stable lookup key is `error.code`; `error.category` is the coarse class for programmatic handling.

```json
{
  "error": {
    "code": "KA-INPUT-001",
    "category": "user_input_error",
    "message": "Request validation failed.",
    "retryable": false
  },
  "detail": "Request validation failed."
}
```

See [Error Codes](ERROR_CODES.md) for the full catalog.

Unexpected server exceptions are also converted to this envelope with
`KA-INTERNAL-001`; public API clients should never need to parse Python
tracebacks.

## Health

```http
GET /health
```

Returns service availability. Use this before triggering long-running jobs from external clients.

## Diagnostics

```http
GET /doctor
GET /doctor?config_path=/path/to/config.yaml&connector=markdown
```

Runs read-only setup diagnostics for config loading, vault structure, model
environment, connector discovery, optional document preprocessing, and recent
run state. It does not call a model and does not write wiki pages.

## Synchronous Workflows

Use synchronous endpoints when the caller can wait for completion.

### Ingest configured sources

```http
POST /ingest/run
```

Runs enabled connectors from `config.yaml`, normalizes sources, applies checkpoints and segmentation, compiles approved wiki pages, writes reports, and updates ledgers.

### Ingest one normalized document

```http
POST /ingest/document
```

Runs ingest for one `source_document.v1` payload. Use this when another adapter has already normalized input.

### Ingest one file path

```http
POST /ingest/file
```

Runs ingest for one local file path. Markdown runs directly. Rich documents such as PDF/DOCX/PPTX require a configured document preprocessor such as MinerU.

### Lint maintenance

```http
POST /lint/run
```

Runs deterministic lint plus optional semantic structural or quality maintenance, according to the request mode.

### Query local wiki context

```http
POST /query/search
```

Retrieves relevant wiki pages, excerpts, related context, trace data, and a prompt-ready context pack. KnoArbor does not generate the final chat answer; the host AI decides how to use returned evidence.

Set `write_report: true` in the request body to write a query audit report. The response then includes `stats.query_report_path`, for example `maintenance/query_report_20260527_120000_000000.md`.

By default, query returns a bounded `compact` context pack for host AI tools. Set `context_format: "full"` when the caller wants complete matched wiki page bodies instead of a compressed context pack. Full mode still limits the number of returned pages through `max_results` and retrieval ranking, but it does not truncate the returned page bodies.

The response carries an explicit contract version:

```json
{
  "schema_version": "wiki_query.v1",
  "query": "agent loop",
  "retrieval_mode": "machine_hybrid_balanced",
  "results": [],
  "context_pack": "...",
  "trace": {
    "schema_version": "query_trace.v1",
    "initial_scope_dirs": ["concepts"],
    "expanded_scope_dirs": ["concepts", "entities", "sources"],
    "origin_counts": { "direct": 1, "related": 2 },
    "returned_paths": ["concepts/Agent-Loop.md"]
  }
}
```

`results` are evidence candidates, not final citations. `match_kind` explains whether a page matched the query directly or entered through the wiki link graph. Host AIs should decide which returned pages to cite based on relevance, excerpts, summaries, and their own task context.

## Model Usage Telemetry

Workflow reports and run metrics include model usage fields when the selected provider returns them:

- `semantic_calls`
- `total_tokens`
- `tokens_per_second`
- `prompt_cached_tokens`
- `prompt_cache_hit_tokens`
- `prompt_cache_miss_tokens`

Prompt caching is provider-owned. KnoArbor does not require a cache switch in `config.yaml`; it keeps long semantic contract prompts stable and records cache telemetry only when the model API returns cache fields. Missing cache fields mean the provider did not report them, not that the run failed.

### Query feedback

```http
POST /query/feedback
```

Records whether retrieved pages were useful. This supports later ranking improvements.

### Query trends

```http
GET /query/trends?obsidian_vault_path=/path/to/wiki&limit=100
```

Returns recent no-result and low-confidence query trends from the query ledger. This endpoint is read-only and is intended for dashboarding and future maintenance planning.

## Asynchronous Runs

Use `/runs/*` for long-running work. This is the recommended API for UI, Apifox tests, and external workflow systems because it exposes queue state, heartbeats, events, cancellation, metrics, and final summaries.

### Start runs

```http
POST /runs/ingest
POST /runs/ingest-file
POST /runs/lint
POST /runs/query
```

Each endpoint returns:

```json
{
  "run_id": "20260525_123456_abcdef",
  "status": "queued",
  "run": {
    "schema_version": "run_record.v1",
    "flow": "ingest",
    "stage": "queued"
  }
}
```

### Inspect runs

```http
GET /runs?vault_path=/path/to/wiki&active_only=false&limit=50
GET /runs/active?vault_path=/path/to/wiki&limit=20
GET /runs/{run_id}?vault_path=/path/to/wiki
GET /runs/{run_id}/events?vault_path=/path/to/wiki&after=0&limit=200
GET /runs/{run_id}/stream?vault_path=/path/to/wiki&after=0
```

`/stream` uses Server-Sent Events. Apifox can test the non-stream JSON endpoints directly; curl can follow SSE:

```bash
curl -N "http://127.0.0.1:8000/runs/RUN_ID/stream?vault_path=/absolute/wiki/path"
```

### Cancel runs

```http
POST /runs/{run_id}/cancel?vault_path=/path/to/wiki
```

Cancellation is cooperative. A running model request may finish before the pipeline stops at the next checkpoint.

### Recover ingest runs

```http
POST /runs/{run_id}/rerun-failed?vault_path=/path/to/wiki
```

Recovery creates a new ingest run from the previous run metadata. KnoArbor keeps the source/window checkpoint as the source of truth, so successful unchanged sources are skipped and failed or changed sources can be processed again.

Recovery does not mutate the old run. Inspect the newly returned `run_id` with
`GET /runs/{run_id}` and `GET /runs/{run_id}/events`. Source-level execution
records are appended to `maintenance/ingest_execution_ledger.jsonl` when ingest
recovery is enabled.

## Concurrency Model

KnoArbor currently uses a local single-machine queue:

- Runs are serialized per wiki vault to protect page writes, ledgers, checkpoints, and index updates.
- Runs for different vaults may execute independently.
- DeepSeek/OpenAI-compatible model calls can technically be concurrent. KnoArbor exposes bounded source-level concurrency for dry-run/preflight ingest, but write-capable ingest remains serial inside one vault.
- Future write-capable source/segment concurrency must aggregate drafts before writing and commit checkpoints only after the whole source succeeds.

This design favors correctness and reproducibility over maximum throughput for the first public version.

## Wiki Page API

Use these endpoints to inspect generated wiki pages from a UI, skill, CLI wrapper, or external tool.

```http
GET /wiki/pages?vault_path=/path/to/wiki
GET /wiki/page?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
GET /wiki/backlinks?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
```

`/wiki/pages` returns page summaries and link metadata. `/wiki/page` returns one Markdown page with metadata and rendered summary fields. `/wiki/backlinks` returns pages that link to the selected page.

These routes are stable public read APIs. The local UI uses them too; external tools should depend on `/wiki/*` instead of `/ui/api/*`.

## UI Endpoints

The management UI is served at:

```http
GET /
GET /ui
```

`/ui/api/*` endpoints are internal to the local console. They may change as the UI evolves and should not be treated as stable integration points.

## Removed Low-Level Endpoints

Prototype-only connector, page-read, draft-write, scan, and operation execution endpoints are no longer public. Use the high-level pipeline and run APIs above.

## Architecture Boundary

FastAPI is an adapter over Python Core. It should not own prompt contracts, model routing, page rendering rules, or vault policy. Those belong to the core, semantic, pipeline, storage, and runtime layers.
