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

Public endpoints are organized by product capability, not by internal workflow shape. Variants are selected by request parameters.

| Area | Endpoint | Purpose |
| --- | --- | --- |
| Service status | `GET /health` | Lightweight service heartbeat |
| Diagnostics | `GET /doctor` | Read-only setup checks |
| Ingest | `POST /ingest` | Compile configured sources, one normalized document, one file, or recover a failed ingest |
| Lint | `POST /lint` | Run deterministic, structural, quality, or full maintenance |
| Query | `POST /query` | Retrieve wiki context for a host AI |
| Query telemetry | `POST /query/feedback`, `GET /query/trends` | Record and inspect query usefulness signals |
| Run monitor | `GET /runs`, `GET /runs/{run_id}` | Inspect queued/running/completed workflows |
| Run events | `GET /runs/{run_id}/events`, `GET /runs/{run_id}/stream`, `POST /runs/{run_id}/cancel` | Observe or cancel a run |
| Wiki pages | `GET /wiki/pages`, `GET /wiki/pages/content`, `GET /wiki/pages/links` | Read generated wiki pages |

`/ui/api/*` is reserved for the local management UI and is not a stable integration API.

## Execution Model

`/ingest` and `/lint` support:

- `execution: "queued"`: returns a `run_id` immediately and records progress under `/runs`.
- `execution: "direct"`: blocks until the workflow completes and returns the workflow output in `result`.

Default execution is `queued`, because ingest and semantic lint can call models and may take time. `/query` stays direct because it is a read-only retrieval endpoint intended for host AI tools.

Both endpoints always return the same workflow envelope:

```json
{
  "flow": "ingest",
  "execution": "queued",
  "status": "queued",
  "run_id": "20260525_123456_abcdef",
  "run": { "schema_version": "run_record.v1" },
  "result": null
}
```

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
GET /doctor?check_model_runtime=false&check_connector_runtime=false
```

Runs read-only setup diagnostics for config loading, vault structure, model environment, connector discovery, optional document preprocessing, and recent run state. It never writes wiki pages. Runtime checks are controlled by query parameters:

- `check_model_runtime`: when `true`, tests the configured model endpoint and structured-output support.
- `check_connector_runtime`: when `true`, runs connector discovery and reports discovered source counts.

Use `false` for UI/on-load checks and `true` for explicit readiness tests.

## Ingest

```http
POST /ingest
```

Use `kind` to select the input shape:

- `connectors`: run configured source connectors.
- `file`: ingest one local input file.
- `document`: ingest one already normalized `source_document`.
- `recovery`: retry failed items from a previous ingest run.

Configured sources:

```json
{
  "execution": "queued",
  "kind": "connectors",
  "config_path": "./config.yaml",
  "connector_names": ["markdown"],
  "write": true
}
```

One local file:

```json
{
  "execution": "queued",
  "kind": "file",
  "config_path": "./config.yaml",
  "input_path": "/path/to/file.pdf",
  "write": true
}
```

One normalized source document:

```json
{
  "execution": "queued",
  "kind": "document",
  "source_document": { "schema_version": "source_document.v1" },
  "write": true
}
```

Recover a failed ingest run:

```json
{
  "execution": "queued",
  "kind": "recovery",
  "recovery_vault_path": "/path/to/wiki",
  "recovery_of_run_id": "20260525_123456_abcdef",
  "write": true
}
```

`kind: "recovery"` only supports `execution: "queued"` because it is tied to a previous run record and may replay multiple failed items.

Markdown files run directly. Rich documents such as PDF/DOCX/PPTX require a configured document preprocessor such as MinerU.
The response always uses the workflow envelope described in [Execution Model](#execution-model).

## Lint

```http
POST /lint
```

Runs deterministic lint plus optional semantic structural or quality maintenance. `mode` controls behavior:

- `deterministic`
- `semantic_structural`
- `semantic_quality`
- `semantic_full`

Example:

```json
{
  "execution": "queued",
  "vault_path": "/path/to/wiki",
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
```

## Query

```http
POST /query
```

Retrieves relevant wiki pages, excerpts, related context, trace data, and a prompt-ready context pack. KnoArbor does not generate the final chat answer; the host AI decides how to use returned evidence.

```json
{
  "vault_path": "/path/to/wiki",
  "query": "agent loop",
  "mode": "balanced",
  "context_format": "compact"
}
```

By default, query returns a bounded `compact` context pack. Set `context_format: "full"` when the caller wants complete matched wiki page bodies instead of a compressed context pack.

## Query Telemetry

```http
POST /query/feedback
GET /query/trends?vault_path=/path/to/wiki&limit=100
```

Feedback records whether retrieved pages were useful. Trends return recent no-result and low-confidence query patterns from the query ledger.

## Run Monitor

Inspect runs:

```http
GET /runs?vault_path=/path/to/wiki&active_only=false&limit=50
GET /runs/{run_id}?vault_path=/path/to/wiki
GET /runs/{run_id}/events?vault_path=/path/to/wiki&after=0&limit=200
GET /runs/{run_id}/stream?after=0
POST /runs/{run_id}/cancel
```

`/stream` uses Server-Sent Events:

```bash
curl -N "http://127.0.0.1:8000/runs/RUN_ID/stream"
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
GET /wiki/pages/content?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
GET /wiki/pages/links?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
```

`/wiki/pages` returns page summaries and link metadata. `/wiki/pages/content` returns one Markdown page with metadata and rendered summary fields. `/wiki/pages/links` returns pages that link to the selected page.

## UI Endpoints

The management UI is served at:

```http
GET /
GET /ui
```

`/ui/api/*` endpoints are internal to the local console. They may change as the UI evolves and should not be treated as stable integration points.

## Removed Low-Level Endpoints

Prototype connector, page-read, draft-write, scan, operation execution, old split workflow endpoints, and generic run-start endpoints are not public. Use `POST /ingest`, `POST /lint`, `POST /query`, and the run monitor endpoints above.

## Architecture Boundary

FastAPI is an adapter over Python Core. It should not own prompt contracts, model routing, page rendering rules, or vault policy. Those belong to the core, semantic, pipeline, storage, and runtime layers.
