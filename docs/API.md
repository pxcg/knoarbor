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
| Runtime context | `GET /runtime` | Discover the active local API URL, config path, vault path, and endpoint file |
| Diagnostics | `GET /doctor` | Read-only setup checks |
| Sources | `GET /sources` | Read source connector capability catalog |
| Ingest | `POST /ingest` | Compile configured sources, one normalized document, one file or folder, or recover a failed ingest |
| Lint | `POST /lint` | Run deterministic, structural, quality, or full maintenance |
| Query | `POST /query` | Retrieve wiki context for a host AI |
| Query telemetry | `POST /query/feedback`, `GET /query/trends` | Record and inspect query usefulness signals |
| Reports | `GET /reports`, `GET /reports/content` | List and read workflow reports |
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

## Vault Selection

Read APIs accept either an explicit `vault_path` or a configured `vault_id`.
Use `vault_id` when integrating with a shared `config.yaml`; use `vault_path`
for one-off automation. `POST /query` also supports multi-vault retrieval with
`all_vaults: true` or `vault_ids: [...]`; each result is annotated with
`vault_id`, `vault_name`, and `vault_path`.

```http
POST /query
GET /wiki/pages?vault_id=personal
GET /reports?vault_id=personal
GET /runs?vault_id=personal
```

When an API call must resolve `vault_id` from a non-default config file, pass
`config_path` alongside `vault_id`.

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

## Runtime Context

```http
GET /runtime
```

Returns the active local runtime context for host AI tools, shell scripts, and
HTTP-only integrations:

```json
{
  "schema_version": "runtime_context.v1",
  "service_online": true,
  "base_url": "http://127.0.0.1:8000",
  "config_path": "/path/to/config.yaml",
  "vault_path": "/path/to/wiki",
  "vault_id": "personal",
  "vault_name": "My Knowledge Base",
  "vaults": [
    {
      "id": "personal",
      "name": "My Knowledge Base",
      "path": "/path/to/wiki"
    }
  ],
  "endpoint_path": "/path/to/.knoarbor/endpoint.json",
  "user_endpoint_path": "~/.knoarbor/endpoint.json",
  "errors": []
}
```

Use this instead of `/ui/api/*` when an integration needs to discover the
current vault path. If the service auto-selects a different port, `knoar serve`
also writes the same runtime address to the user-level
`.knoarbor/endpoint.json` and to the project-local `.knoarbor/endpoint.json`
next to `config.yaml`.

## Reports

```http
GET /reports?vault_path=/path/to/wiki
GET /reports/content?vault_path=/path/to/wiki&path=maintenance/ingest_report_YYYYMMDD_HHMMSS.md
```

Lists or reads Markdown workflow reports from the vault `maintenance/` folder.
`GET /reports` also accepts `all_vaults=true` or repeated `vault_ids` with
`config_path`; each returned report includes `vault_id`, `vault_name`, and
`vault_path`. Reading one report still requires a single vault selector.
Reports are public integration APIs because host AI tools often need to explain
what changed, what failed, or which pages were written after a run.

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

## Sources

```http
GET /sources
GET /sources?config_path=/path/to/config.yaml&connector=markdown
```

Returns the source connector capability catalog without scanning local files.
Use this endpoint when an external tool needs to know which input sources
KnoArbor supports, which `source_type` values each connector emits, and whether
a connector supports checkpointing or segmentation hints. Each connector also
includes a lightweight `settings_schema` describing supported config fields,
such as `roots`, `sessions_dir`, `session_files`, `pattern`, and `recursive`.

When `config_path` is provided, each catalog item is annotated with:

- `configured`: whether that connector appears in the config file.
- `enabled`: whether that connector is enabled in the config file.

Source file discovery remains part of `GET /doctor` runtime checks and the
`knoar sources` CLI preflight command.

## Ingest

```http
POST /ingest
```

Use `kind` to select the input shape:

- `connectors`: run configured source connectors.
- `file`: ingest one local input file.
- `folder`: ingest one local folder as a one-off input without changing persistent configuration.
- `document`: ingest one already normalized `source_document`.
- `recovery`: retry failed items from a previous ingest run.

Ingest is a write workflow and always targets one vault per request. Select that
vault with `vault_path`, or use `config_path` plus `vault_id` for a configured
vault. It intentionally does not support `all_vaults=true`; start one run per
vault when multiple knowledge bases need to be compiled.

Configured sources:

```json
{
  "execution": "queued",
  "kind": "connectors",
  "config_path": "./config.yaml",
  "vault_id": "personal",
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
  "vault_id": "personal",
  "input_path": "/path/to/file.pdf",
  "write": true
}
```

One local folder:

```json
{
  "execution": "queued",
  "kind": "folder",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "input_path": "/path/to/folder",
  "recursive": true,
  "write": true
}
```

Folder ingest discovers Markdown files directly. Non-Markdown files in the folder
require the configured MinerU-compatible preprocessor. If preprocessing is not
enabled or fails, the run fails explicitly instead of silently skipping files.

One normalized source document:

```json
{
  "execution": "queued",
  "kind": "document",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "source_document": { "schema_version": "source_document.v1" },
  "write": true
}
```

Recover a failed ingest run:

```json
{
  "execution": "queued",
  "kind": "recovery",
  "config_path": "./config.yaml",
  "vault_id": "personal",
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

Lint is also a write-capable maintenance workflow and targets one vault per
request. Use `vault_path`, or use `config_path` plus `vault_id` for a configured
vault. Cross-vault summaries are available through `/reports` and `/runs`, but
maintenance itself should be started separately for each vault.

Example:

```json
{
  "execution": "queued",
  "config_path": "./config.yaml",
  "vault_id": "personal",
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

Configured multi-vault query:

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "all_vaults": true,
  "mode": "balanced",
  "context_format": "compact"
}
```

Selected-vault query:

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "vault_ids": ["personal", "team"],
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

`GET /runs` also accepts `all_vaults=true` or repeated `vault_ids` with
`config_path`; each returned run includes `vault_id`, `vault_name`, and
`vault_path`. Single-run read, event, stream, and cancel operations require one
vault selector because run IDs are vault-local.

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

These endpoints also accept `vault_id` with `config_path`. When a result from
a multi-vault `/query` response is selected, pass the result's `vault_id` to
read or inspect the page in the same knowledge base.

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
