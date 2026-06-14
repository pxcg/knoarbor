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
| Vault registry | `GET /vaults` | List configured knowledge-base vaults with IDs, names, paths, and availability |
| Diagnostics | `GET /doctor` | Read-only setup checks |
| Sources | `GET /sources` | Read source connector capability catalog |
| Models | `GET /models/providers`, `POST /models/discover`, `POST /models/probe`, `POST /models/apply-capabilities` | List configured providers, discover runtime model metadata, run bounded model probes, and explicitly apply detected limits |
| Ingest | `POST /ingest` | Compile configured sources, one normalized document, one file or folder, or recover a failed ingest |
| Lint | `POST /lint` | Run deterministic, structural, quality, or full maintenance |
| Query | `POST /query` | Retrieve wiki context for a host AI |
| Chat | `POST /chat` | Ask the selected vault through the bounded KnoArbor Wiki Chat Agent |
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
  "schema_version": "workflow_response.v1",
  "flow": "ingest",
  "execution": "queued",
  "status": "queued",
  "run_id": "20260525_123456_abcdef",
  "run": { "schema_version": "run_record.v1" },
  "result": null
}
```

`schema_version` is the compatibility marker for workflow responses. Clients
should branch on `execution` only to decide whether to inspect `run_id`/`run`
or `result`; the top-level fields stay present in both modes. `/query` is not a
workflow response: it returns `schema_version: "wiki_query.v1"` with retrieval
results directly.

## Chat

```http
POST /chat
```

Runs the bounded KnoArbor Wiki Chat Agent. Chat supports two execution styles:
`agentic` lets a strong model decide which KnoArbor tool to call, while
`retrieval_first` lets KnoArbor search the wiki first and asks the model only to
synthesize an answer from the evidence pack. `auto` uses `retrieval_first` for
local Ollama/vLLM providers and `agentic` for other providers. Chat can search
maintained wiki pages, read pages, inspect reports and runs, list sources, and
queue explicitly requested ingest or lint workflows. It does not expose
arbitrary shell, browser, filesystem, or network tools.

Example request:

```json
{
  "schema_version": "chat_request.v1",
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "messages": [
    {"role": "user", "content": "Agent Loop 是什么？"}
  ],
  "mode": "balanced",
  "execution_mode": "auto",
  "max_turns": 6,
  "include_trace": true
}
```

Example response:

```json
{
  "schema_version": "chat_response.v1",
  "answer": "Agent Loop is...",
  "citations": [
    {"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}
  ],
  "tool_trace": [
    {"tool": "search_wiki", "status": "ok", "summary": "Found 3 wiki result(s)."}
  ],
  "run_links": [],
  "memory_used": [],
  "memory_candidates": [],
  "memory_writes": [],
  "stats": {"execution_mode": "retrieval_first", "model_calls": 1, "tool_calls": 1, "memory_used": 0, "memory_writes": 0, "total_tokens": 1200},
  "warnings": []
}
```

Use `/chat` when KnoArbor should synthesize an answer inside the console. Use
`/query` when another host AI should receive evidence and generate the final
answer itself.

## Vault Selection

Vaults are first-class knowledge-base spaces. Public integrations should prefer
`config_path + vault_id` because the ID is stable when local paths move. Use
`vault_path` for one-off automation or temporary vaults.

Read the registry before selecting a vault:

```http
GET /vaults?config_path=/path/to/config.yaml
```

The response returns the configured default vault and each profile's `id`,
display `name`, resolved `path`, active state, and availability.

`POST /query` also supports multi-vault retrieval with `all_vaults: true`,
`vault_id: "all"`, or `vault_ids: [...]`; each result is annotated with
`vault_id`, `vault_name`, and `vault_path`. `all` is a reserved virtual scope,
not a writable vault profile.

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
  "vault_path": "/path/to/vault",
  "vault_id": "personal",
  "vault_name": "My Knowledge Base",
  "vaults": [
    {
      "id": "personal",
      "name": "My Knowledge Base",
      "path": "/path/to/vault"
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

## Vault Registry

```http
GET /vaults
GET /vaults?config_path=/path/to/config.yaml
```

Returns configured knowledge-base profiles:

```json
{
  "schema_version": "vaults.v1",
  "config_path": "/path/to/config.yaml",
  "default_vault_id": "personal",
  "vaults": [
    {
      "id": "personal",
      "name": "Personal Knowledge Base",
      "path": "/path/to/vault",
      "active": true,
      "exists": true
    }
  ]
}
```

Use this endpoint when an integration needs a stable `vault_id` before calling
query, page, report, run, ingest, or lint APIs. `path` is still returned for
local inspection and one-off automation, but public clients should prefer
`vault_id` where available.

## Reports

```http
GET /reports?vault_path=/path/to/vault
GET /reports/content?vault_path=/path/to/vault&path=maintenance/ingest_report_YYYYMMDD_HHMMSS.md
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

## Models

```http
GET /models/providers
POST /models/discover
POST /models/probe
POST /models/apply-capabilities
```

Model endpoints expose the configured model registry and the runtime checks
needed before long semantic workflows. They are safe to call from Swagger,
Apifox, scripts, and the local UI.

`GET /models/providers` reads the current provider registry without calling a
model endpoint. It hides API keys and reports only whether the configured key
environment variable is available.

`POST /models/discover` calls the provider model-list endpoint, such as
OpenAI-compatible `/models`. For Ollama-style endpoints, KnoArbor also attempts
`/api/show` to detect context length. Discovery does not generate model tokens.

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "vllm"
}
```

`POST /models/probe` performs a bounded generation request. `level:
"minimal"` verifies chat completion connectivity with a tiny `OK` response.
`level: "structured"` verifies whether the selected model can satisfy the
structured JSON contract used by KnoArbor agents.

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "deepseek",
  "level": "structured"
}
```

`POST /models/apply-capabilities` is the only model endpoint that writes
configuration. It explicitly stores detected or user-selected fields such as
`context_window`, `max_output_tokens`, and `json_mode`; discovery and probe
responses only suggest values.

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "vllm",
  "context_window": 32768,
  "max_output_tokens": 8000,
  "json_mode": false
}
```

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

Retrieves relevant wiki pages, excerpts, related context, trace data, and a
prompt-ready context pack. KnoArbor does not generate the final chat answer;
the host AI decides how to use returned evidence.

Query is page-first rather than chunk-first. Returned pages are still listed in
ranked `results`, and each result has a `role`:

- `primary`: the maintained wiki page that most directly answers the query.
- `supporting`: related maintained pages that add implementation details,
  caveats, comparisons, or follow-up context.
- `source`: source digest pages that provide provenance.

The response also groups those same result objects as `primary_pages`,
`supporting_pages`, and `source_pages`. Callers may cite any returned page, but
ordinary answers should usually start from the primary page's structured wiki
content and use supporting/source pages as needed.

The context pack is page-first, not chunk-first: it preserves the primary page
body as the maintained answer unit, while supporting and source pages are
returned as structured summaries, key points, excerpts, and source pointers.
Call `/wiki/pages/content` when the caller needs to read the full body of a
specific supporting page.

The response also includes:

- `answer_scope`: whether the query is narrow, broad, or exploratory, plus the
  vault and directory scope used for retrieval.
- `answer_set`: path-level grouping for the recommended answer set. Narrow
  questions often use one primary page; broad questions can include several
  supporting pages because each wiki page is a curated knowledge unit.
- `evidence_coverage`: a compact signal for whether the returned pages provide
  strong, adequate, or weak local coverage.

```json
{
  "vault_path": "/path/to/vault",
  "query": "agent loop",
  "mode": "balanced"
}
```

Configured multi-vault query:

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "all_vaults": true,
  "mode": "balanced"
}
```

Selected-vault query:

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "vault_ids": ["personal", "team"],
  "mode": "balanced"
}
```

## Query Telemetry

```http
POST /query/feedback
GET /query/trends?vault_path=/path/to/vault&limit=100
```

Feedback records whether retrieved pages were useful. Trends return recent no-result and low-confidence query patterns from the query ledger.

## Run Monitor

Inspect runs:

```http
GET /runs?vault_path=/path/to/vault&active_only=false&limit=50
GET /runs/{run_id}?vault_path=/path/to/vault
GET /runs/{run_id}/events?vault_path=/path/to/vault&after=0&limit=200
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

Ingest, lint, and chat model calls are also appended to
`maintenance/token_ledger.jsonl` with `flow=ingest`, `flow=lint`, or
`flow=chat`. The Token Analytics page reads this ledger to compare usage by
workflow, agent, source, page, provider, and model.

## Concurrency Model

KnoArbor currently uses a local single-machine queue:

- Runs are serialized per wiki vault to protect page writes, ledgers, checkpoints, and index updates.
- Runs for different vaults may execute independently.
- Write-capable ingest remains serial inside one vault.
- Future write-capable source/segment concurrency must aggregate drafts before writing and commit checkpoints only after the whole source succeeds.

This design favors correctness and reproducibility over maximum throughput for the first public version.

## Wiki Page API

```http
GET /wiki/pages?vault_path=/path/to/vault
GET /wiki/pages/content?vault_path=/path/to/vault&path=concepts/Agent-Loop.md
GET /wiki/pages/links?vault_path=/path/to/vault&path=concepts/Agent-Loop.md
```

`/wiki/pages` returns page summaries and link metadata. `/wiki/pages/content`
returns one Markdown page with metadata and rendered summary fields.
`/wiki/pages/links` returns pages that link to the selected page. Page paths are
relative to the maintained content root, so callers pass
`concepts/Agent-Loop.md` even though the default filesystem location is
`vaults/all/pages/concepts/Agent-Loop.md`.

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
