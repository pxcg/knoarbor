# API Reference

KnoArbor exposes a compact local HTTP API for the UI, CLI wrappers, workflow tools, and AI-tool skills. The API is JSON over HTTP and can be called from Swagger, Apifox, Postman, curl, Python, or any OpenAPI-compatible client.

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

## Design Rule

KnoArbor keeps the public API intentionally small. Different workflow variants are selected by request parameters, not by adding many separate endpoints.

| Area | Endpoint | Purpose |
| --- | --- | --- |
| Service status | `GET /health` | Lightweight service heartbeat |
| Diagnostics | `GET /doctor` | Read-only setup checks |
| Synchronous ingest | `POST /ingest` | Compile configured sources, one normalized document, or one file |
| Lint maintenance | `POST /lint/run` | Run deterministic, structural, quality, or full maintenance |
| Query | `POST /query/search` | Retrieve wiki context for a host AI |
| Query feedback | `POST /query/feedback`, `GET /query/trends` | Record and inspect query usefulness signals |
| Run queue | `POST /runs`, `GET /runs`, `GET /runs/{run_id}` | Start and inspect long-running workflows |
| Run events | `GET /runs/{run_id}/events`, `GET /runs/{run_id}/stream`, `POST /runs/{run_id}/cancel` | Observe or cancel a run |
| Wiki pages | `GET /wiki/pages`, `GET /wiki/page`, `GET /wiki/backlinks` | Read generated wiki pages |

`/ui/api/*` is reserved for the local management UI and is not a stable integration API.

## Compatibility Policy

The endpoints in this document are the v0.x public alpha API surface. Paths, methods, required request fields, and core response meanings are intended to remain stable during the v0.x line. Response schemas may receive additive optional fields before a later stable release.

The machine-readable compatibility list lives in `src/knoarbor/entrypoints/api_contract.py`; API surface tests read that contract directly.

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

## Health

```http
GET /health
```

Returns service availability. Use this before triggering long-running jobs.

## Diagnostics

```http
GET /doctor
GET /doctor?config_path=/path/to/config.yaml&connector=markdown
```

Runs read-only setup diagnostics for config loading, vault structure, model environment, connector discovery, optional document preprocessing, and recent run state. It does not call a model and does not write wiki pages.

## Ingest

```http
POST /ingest
```

Runs ingest synchronously. Use `kind` to select the input shape:

```json
{ "kind": "connectors", "config_path": "./config.yaml", "connector_names": ["markdown"], "write": true }
```

```json
{ "kind": "file", "config_path": "./config.yaml", "input_path": "/path/to/file.pdf", "write": true }
```

```json
{ "kind": "document", "source_document": { "schema_version": "source_document.v1" }, "write": true }
```

Markdown files run directly. Rich documents such as PDF/DOCX/PPTX require a configured document preprocessor such as MinerU.

## Lint

```http
POST /lint/run
```

Runs deterministic lint plus optional semantic structural or quality maintenance. `mode` controls the behavior:

- `deterministic`
- `semantic_structural`
- `semantic_quality`
- `semantic_full`

## Query

```http
POST /query/search
```

Retrieves relevant wiki pages, excerpts, related context, trace data, and a prompt-ready context pack. KnoArbor does not generate the final chat answer; the host AI decides how to use returned evidence.

By default, query returns a bounded `compact` context pack. Set `context_format: "full"` when the caller wants complete matched wiki page bodies instead of a compressed context pack.

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

`results` are evidence candidates, not final citations. `match_kind` explains whether a page matched the query directly or entered through the wiki link graph.

## Query Feedback

```http
POST /query/feedback
GET /query/trends?obsidian_vault_path=/path/to/wiki&limit=100
```

Feedback records whether retrieved pages were useful. Trends return recent no-result and low-confidence query patterns from the query ledger.

## Long-Running Runs

```http
POST /runs
```

Starts a queued workflow. Use `flow` to select the workflow.

Ingest connectors:

```json
{
  "flow": "ingest",
  "ingest": { "kind": "connectors", "config_path": "./config.yaml", "write": true }
}
```

Ingest a file:

```json
{
  "flow": "ingest",
  "ingest": { "kind": "file", "config_path": "./config.yaml", "input_path": "/path/to/file.pdf", "write": true }
}
```

Run lint:

```json
{
  "flow": "lint",
  "lint": {
    "obsidian_vault_path": "/path/to/wiki",
    "mode": "semantic_structural",
    "scope": {
      "scope_id": "manual:api",
      "trigger": "manual",
      "source": { "kind": "api" },
      "changed_pages": [],
      "recommended_lint_modes": ["semantic_structural"],
      "reason": "Manual maintenance run."
    }
  }
}
```

Run query:

```json
{
  "flow": "query",
  "query": { "obsidian_vault_path": "/path/to/wiki", "query": "agent loop" }
}
```

Recover a failed ingest run:

```json
{
  "flow": "ingest",
  "vault_path": "/path/to/wiki",
  "recovery_of_run_id": "20260525_123456_abcdef",
  "recovery": { "write": true }
}
```

The response is:

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

Inspect runs:

```http
GET /runs?vault_path=/path/to/wiki&active_only=false&limit=50
GET /runs/{run_id}?vault_path=/path/to/wiki
GET /runs/{run_id}/events?vault_path=/path/to/wiki&after=0&limit=200
GET /runs/{run_id}/stream?vault_path=/path/to/wiki&after=0
POST /runs/{run_id}/cancel?vault_path=/path/to/wiki
```

`/stream` uses Server-Sent Events:

```bash
curl -N "http://127.0.0.1:8000/runs/RUN_ID/stream?vault_path=/absolute/wiki/path"
```

Cancellation is cooperative. A running model request may finish before the pipeline stops at the next checkpoint.

## Model Usage Telemetry

Workflow reports and run metrics include model usage fields when the selected provider returns them:

- `semantic_calls`
- `total_tokens`
- `tokens_per_second`
- `prompt_cached_tokens`
- `prompt_cache_hit_tokens`
- `prompt_cache_miss_tokens`

Prompt caching is provider-owned. KnoArbor keeps long semantic contract prompts stable and records cache telemetry only when the model API returns cache fields.

## Concurrency Model

KnoArbor currently uses a local single-machine queue:

- Runs are serialized per wiki vault to protect page writes, ledgers, checkpoints, and index updates.
- Runs for different vaults may execute independently.
- Write-capable ingest remains serial inside one vault.
- Future write-capable source/segment concurrency must aggregate drafts before writing and commit checkpoints only after the whole source succeeds.

This design favors correctness and reproducibility over maximum throughput for the first public version.

## Wiki Page API

```http
GET /wiki/pages?vault_path=/path/to/wiki
GET /wiki/page?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
GET /wiki/backlinks?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
```

`/wiki/pages` returns page summaries and link metadata. `/wiki/page` returns one Markdown page with metadata and rendered summary fields. `/wiki/backlinks` returns pages that link to the selected page.

## UI Endpoints

The management UI is served at:

```http
GET /
GET /ui
```

`/ui/api/*` endpoints are internal to the local console. They may change as the UI evolves and should not be treated as stable integration points.

## Removed Low-Level Endpoints

Prototype connector, page-read, draft-write, scan, operation execution, and old split workflow endpoints are not public. Use `POST /ingest`, `POST /lint/run`, `POST /query/search`, and `POST /runs`.

## Architecture Boundary

FastAPI is an adapter over Python Core. It should not own prompt contracts, model routing, page rendering rules, or vault policy. Those belong to the core, semantic, pipeline, storage, and runtime layers.
