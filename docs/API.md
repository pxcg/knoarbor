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
| Models | `GET /models/providers`, `GET /models/image-providers`, `POST /models/discover`, `POST /models/apply-capabilities` | List configured text/image providers, check runtime model metadata, and explicitly apply selected model settings |
| Ingest | `POST /ingest`, `POST /ingest/materialization/rebuild` | Compile sources or rebuild deterministic views from committed facts |
| Lint | `POST /lint` | Run deterministic structured maintenance or semantic maintenance |
| Query | `POST /query` | Retrieve claim-backed active raw evidence and trace for a host AI |
| Chat | `POST /chat`, `POST /chat/stream`, `POST /chat/citations/resolve`, `GET /chat/sessions`, `GET/PATCH/DELETE /chat/sessions/{session_id}`, `POST /chat/sessions/{session_id}/ingest`, `POST /chat/sessions/{session_id}/close`, `POST /chat/sessions/{session_id}/retry` | Ask the selected vault, stream answers, resolve temporary citation highlights, manage sessions, compile sessions, close sessions, and retry failed answers |
| Query telemetry | `POST /query/feedback`, `GET /query/trends` | Record and inspect query usefulness signals |
| Reports | `GET /reports`, `GET /reports/content` | List and read workflow reports |
| Run monitor | `GET /runs`, `GET /runs/{run_id}` | Inspect queued/running/completed workflows |
| Run events | `GET /runs/{run_id}/events`, `GET /runs/{run_id}/stream`, `POST /runs/{run_id}/cancel` | Observe or cancel a run |
| Wiki pages | `GET /wiki/pages`, `GET /wiki/pages/content`, `GET /wiki/pages/relations` | Read generated wiki pages |

Desktop-local renderer endpoints are reserved for the packaged desktop app and are not stable integration APIs.

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
workflow response: it returns `schema_version: "wiki_query.v4"` with retrieval
results directly.

## Chat

```http
POST /chat
```

Asks the selected vault through the KnoArbor Wiki Chat Agent. Chat first runs
the unified active-Raw retrieval path. It answers from validated Raw evidence
when candidates exist; only a verified `no_match` with the accepted packaged
quality gate may use model general knowledge. The two sources use
separate prompts and every completed turn persists its final provenance.

Example request:

```json
{
  "schema_version": "chat_request.v4",
  "request_id": "req_01",
  "execution_id": "exec_01",
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "message": {"message_id": "msg_01", "role": "user", "content": "Agent Loop 是什么？"},
  "include_trace": true
}
```

Example response:

```json
{
  "schema_version": "chat_response.v4",
  "request_id": "req_01",
  "execution_id": "exec_01",
  "session_id": "chat_01",
  "session_revision": 1,
  "turn_id": "turn_01",
  "answer": "Agent Loop is...",
  "answer_provenance": {
    "mode": "knowledge_grounded",
    "query_outcome": "candidates",
    "chat_outcome": "sufficient"
  },
  "citations": [
    {"kind": "raw_evidence", "evidence_id": "evh:01", "raw_revision_id": "rawrev:01", "source_unit_id": "unit:01"}
  ],
  "tool_trace": [
    {"tool": "retrieve_knowledge_batch", "status": "ok", "summary": "Returned active Raw evidence."}
  ],
  "run_links": [],
  "memory_used": [],
  "memory_candidates": [],
  "memory_writes": [],
  "stats": {"retrieval_strategy": "fast_unified_recall", "model_calls": 1, "tool_calls": 2},
  "warnings": []
}
```

Use `/chat` when KnoArbor should synthesize an answer inside the console. Chat
optionally uses one dialogue-aware Corpus Tree Navigator to select visible
source or outline nodes, then retrieves the unchanged literal question together
with typed tree scopes in one batch. Outline scopes seed their active Raw
subtrees without another lexical title search. Use `/query` when another host AI should receive
evidence and generate the final answer itself. Use `/ingest` and `/lint`
directly for write or maintenance workflows.

A continuation supplies the persisted `session_id` and its latest
`expected_session_revision`. Stale revisions fail with a storage conflict;
reusing the same `request_id` returns the already persisted turn instead of
appending a duplicate.

Candidate and typed `no_match` results enter the same unified Final Answer
model. It receives the original user request, dialogue-only history, retrieval
outcome, and current Raw evidence, then returns one whole-response mode:
Raw-grounded, general knowledge, or knowledge gap. Code validates support and
derives provenance; it does not use a no-match gate or local-material keyword
router. A normal completed knowledge turn therefore has at most the Retrieval
Planner and Final Answer semantic stages, excluding retries and optional image
generation.

For UI clients that need visible progress during retrieval and answer
synthesis, use the streaming variant:

```http
POST /chat/stream
```

`/chat/stream` accepts the same request body as `/chat` and returns
`text/event-stream`. It emits progress events while the same chat loop is
running, then emits a final event whose `response` field is the same
`chat_response.v4` object returned by `POST /chat`.

Event types:

- `stage`: the chat loop moved to planning, retrieval, or answer generation.
- `tool`: a bounded KnoArbor tool was called or completed.
- `source`: the code-selected provisional answer path (`local_knowledge` or
  model general knowledge) before generation.
- `answer_delta`: incremental final-answer text from the provider adapter.
- `final`: final answer, citations, trace, token stats, and persisted session
  metadata.
- `error`: shared KnoArbor error envelope for failed runs.

Citation previews resolve answer-selected text without storing Raw excerpts in
the chat session:

```http
POST /chat/citations/resolve
```

The request carries one vault selector and the existing locator-only citations.
One Raw citation can carry multiple exact `spans`; the response returns the
corresponding temporary `texts` plus the first `text` by request index.
Resolution reads the identified immutable source unit and interprets every
range in that unit's coordinate space; it does not rerun ingest or call a
model. Missing source material returns `status: "unavailable"` and clients open
Raw without highlighting instead of applying ranges to the complete document.

Chat sessions are stored outside maintained wiki pages. When a conversation
should become durable wiki knowledge, use the chat-session ingest endpoint:

`GET /chat/sessions` accepts `limit` (maximum 200 per page) and `offset`.
The response includes `total_count`, normalized `offset` and `limit`, and
`has_more`; clients follow continuation to reach older summary records without
loading session transcripts.

```http
POST /chat/sessions/{session_id}/ingest
```

The ingest endpoint converts the persisted session into a `knoarbor_chat`
`SourceDocument` and queues the normal `/ingest` document pipeline. The ingest
run uses the standard document path, including segmentation, page review,
write/report generation, and scoped lint when enabled by ingest configuration.
The response is the same queued workflow envelope used by other long-running
ingest requests.

Mutation requests use compare-and-swap session identity. Session ingest carries
`expected_session_revision` and optional stable `turn_ids`; stale revisions or
missing turn identities fail instead of silently ingesting different content.

To rename a saved chat session:

```http
PATCH /chat/sessions/{session_id}
```

```json
{
  "schema_version": "chat_session_retry_request.v4",
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "expected_session_revision": 8,
  "title": "Agent Loop architecture discussion"
}
```

To regenerate the latest assistant answer in an active session:

```http
POST /chat/sessions/{session_id}/retry
```

The retry endpoint executes against a snapshot that excludes the target answer,
then atomically replaces that turn in one session-revision commit. A failed,
cancelled, or crashed retry leaves the previous answer unchanged.

```json
{
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "target_turn_id": "turn_01",
  "expected_session_revision": 8
}
```

Turn deletion uses `DELETE /chat/sessions/{session_id}/turns/{turn_id}` with a
body containing the vault selector and `expected_session_revision`. Whole
session deletion uses the same compare-and-swap body.

To close a session and optionally trigger the configured auto-ingest policy:

```http
POST /chat/sessions/{session_id}/close
```

The close endpoint records an ingest-candidate summary on the session. It does
not write wiki pages unless `chat.auto_ingest.enabled` is explicitly enabled and
the configured policy matches. Manual `/ingest` for a chat session is always
available.

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
  "endpoint_path": "/path/to/state/endpoint.json",
  "errors": []
}
```

Use this instead of desktop-local renderer endpoints when an integration needs
to discover the current vault path. If the service auto-selects a different
port, `knoar serve` atomically updates the single `state/endpoint.json`
authority beside the active `config.yaml`.

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
GET /reports/content?vault_path=/path/to/vault&path=maintenance/reports/ingest/ingest_report_YYYYMMDD_HHMMSS.md
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
GET /models/image-providers
POST /models/image-probe
POST /models/discover
POST /models/apply-capabilities
```

Model endpoints expose the configured model registry and the provider checks
needed before long semantic workflows. They are safe to call from Swagger,
Apifox, scripts, and the local UI.

`GET /models/providers` reads the current provider registry without calling a
model endpoint. It hides API keys and reports only whether the configured key
is available.

`GET /models/image-providers` reads the configured image-generation provider
registry. Image providers are separate from chat/completion model providers and
are used by the chat `generate_image` tool.

`POST /models/image-probe` explicitly performs one real image generation and
returns only bounded status metadata. It can take normal generation time and
incur provider usage; generated image content and raw responses are not returned.

`POST /models/discover` calls the adapter-specific model-list endpoint.
OpenAI-compatible providers use `/models`; native Ollama providers use
`/api/tags` and `/api/show` to detect model availability and context length.
Discovery does not send a chat completion request or generate model tokens.
When the provider exposes model IDs, the response includes `model_ids` so the
client can let users keep a manually entered model or select one of the
discovered models.

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "vllm"
}
```

`POST /models/apply-capabilities` is the only model endpoint that writes
configuration. It explicitly stores user-selected fields such as
`context_window`, `max_output_tokens`, and `json_mode`; discovery does not
automatically modify `config.yaml`.

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
- `excerpt`: ingest user-selected text such as one quote, insight, or a small group of selected chat messages.
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

Editable excerpt (manual input or selected chat content):

```json
{
  "execution": "queued",
  "kind": "excerpt",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "excerpt_title": "Knowledge grows through relations",
  "excerpt_text": "Knowledge is not a pile of memories; it grows through relations.",
  "excerpt_context": {
    "source_app": "knoarbor_chat",
    "session_id": "chat_123",
    "message_ids": ["assistant:4"]
  },
  "write": true
}
```

Excerpt ingest accepts user-authored text or an editable selection from Chat. The
UI may collect a title and target vault before submission, while the API keeps one
`kind=excerpt` contract. Excerpts still use the normal document ingest path: source
normalization, atom extraction and deterministic validation, factual revision
publication, projection/index materialization, and report generation.

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

To rebuild deterministic source projections and the machine index without
rerunning semantic extraction:

```http
POST /ingest/materialization/rebuild
```

The request selects one vault through query parameters and uses an empty JSON
body. The response reports the reconciled materialization epoch and active
fact/index generations.

## Lint

```http
POST /lint
```

Runs integrity governance for one vault. `mode` controls whether the same
deterministic scan also receives read-only semantic diagnosis:

- `deterministic`
- `semantic`

Lint never patches raw material, canonical facts, provenance, or generated page
content directly. It executes approved findings through the owning ingest or
materialization workflow, then rescans the vault. Repair-plan actions use
`reingest_request`, `index_rebuild_request`, `projection_rebuild_request`, or
`report_only`. Use `vault_path`, or use `config_path` plus `vault_id` for a
configured vault.

Example:

```json
{
  "execution": "queued",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "mode": "semantic",
  "scope": {
    "scope_id": "manual:api",
    "trigger": "manual",
    "source": { "kind": "api" },
    "changed_pages": [],
    "recommended_lint_modes": ["semantic"],
    "reason": "Manual maintenance run."
  }
}
```

## Query

```http
POST /query
```

Retrieves claim-backed active raw evidence, locator metadata, gap signals,
trace data, and a prompt-ready context pack. KnoArbor does not generate the
final chat answer; the host AI decides how to use returned evidence.

`wiki_query.v4` searches the immutable active retrieval snapshot through atom/claim and direct Raw channels. Relation atoms are ordinary lexical locators and resolve through their batch-local `source_claim_ids` to Claims and active Raw. It fuses those signals into vault-scoped
`evidence_handles`, which remain the complete lightweight candidate set.
Query admits answer evidence deterministically and re-resolves only those
handles to complete active `raw_evidence`; lower-ranked unadmitted handles stay
reachable without loading their Raw content. Ranked `results` remain locator
metadata for optional navigation. Channel status, typed outcome, gaps,
warnings, and trace remain separate; Wiki page bodies and atom summaries are
never factual material.
```json
{
  "vault_path": "/path/to/vault",
  "query": "agent loop"
}
```

Configured multi-vault query:

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "all_vaults": true
}
```

Selected-vault query:

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "vault_ids": ["personal", "team"]
}
```

The response sets `exhausted=true` only after both lexical channels required by the query plan have completed. If the resource-safety envelope fires first, status is
`resource_exhausted`, completed handles remain in the response, and
`continuation_cursor` carries an opaque query-, vault-, and snapshot-bound
position. Resume the same single-vault query by returning that cursor:

```json
{
  "vault_path": "/path/to/vault",
  "query": "agent loop",
  "continuation_cursor": "retrieval_cursor.v1..."
}
```

For a multi-vault query, use `continuation_cursors` keyed by vault ID. A cursor
is rejected if the query, vault, or active snapshot generation has changed.
This continuation is a safety boundary, not a top-k or relevance cutoff.

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
`.knoarbor/ledgers/token.jsonl` with `flow=ingest`, `flow=lint`, or
`flow=chat`. The Token Analytics page reads this ledger to compare usage by
workflow, agent, source, page, provider, and model.

## Concurrency Model

KnoArbor uses local persisted tasks with operation-owned execution:

- SQLite claims and a cross-process vault lock serialize factual publication and materialization per vault.
- Runs for different vaults may execute independently.
- Provider calls may use bounded concurrency outside the vault-write critical section.
- The desktop schedules work in its current process; the CLI executes the same task protocol in the foreground. There is no persistent worker service.

This design favors local crash consistency and one lifecycle authority over a distributed queue abstraction.

## Wiki Page API

```http
GET /wiki/pages?vault_path=/path/to/vault
GET /wiki/pages/content?vault_path=/path/to/vault&path=Agent-Loop.md
GET /wiki/pages/relations?vault_path=/path/to/vault&path=Agent-Loop.md
PATCH /wiki/pages/content
DELETE /wiki/pages/content
PATCH /wiki/pages/raw
```

`/wiki/pages` returns page summaries and link metadata. `/wiki/pages/content`
returns one Markdown page with metadata and rendered summary fields.
`/wiki/pages/relations` returns incoming and outgoing page relations for the selected page. Page paths are
relative to the maintained content root. Authored pages and deterministic source
projections use flat paths such as `Agent-Loop.md`. Legacy vaults may retain
historical `sources/...` paths.

`GET /wiki/pages/content` exposes an optional `editable_projection` object for
editable `source_index` pages. `PATCH /wiki/pages/content` accepts that
projection's structured editable fields plus its `base_revision_id`; it never
accepts generated Markdown or evidence content. Saving publishes a new canonical
revision and rematerializes the projection and indexes. Synthesis, existing
claim text, entities, and relations are editable. Claim identities and evidence
mappings remain ingest-owned. A stale `base_revision_id` is rejected instead of
overwriting a newer ingest. The edit applies only to the current Raw revision;
a later Raw ingest creates a fresh projection and does not carry those fields
forward.

`DELETE /wiki/pages/content` accepts the same single-vault selector and relative
page path in its JSON body. Deletion runs through the page service so canonical
source facts and deterministic materialization remain coordinated.

`GET /wiki/pages/content` also exposes `editable_raw` for editable source
projections. `PATCH /wiki/pages/raw` accepts `raw_revision_edit.v1` with the
editor's `base_revision_id` and revised normalized Raw text. It does not run the
semantic extractor inline. Instead it submits the revised source document to
the standard queued ingest coordinator with `force_reprocess=true`. The response
is `workflow_response.v1`; clients monitor the returned `run_id` through the
normal run APIs. The ingest calls the configured model and produces fresh
synthesis, claims, entities, relations, evidence, projection, and indexes. The
submitted parent revision is checked again at publication so stale edits cannot
replace a newer active head.

These endpoints also accept `vault_id` with `config_path`. When a result from
a multi-vault `/query` response is selected, pass the result's `vault_id` to
read or inspect the page in the same knowledge base.

## Desktop-Local Endpoints

During the desktop-first transition, developer builds may still serve the renderer at:

```http
GET /
GET /ui
```

Packaged desktop builds load the renderer from Electron resources instead of the Python service. Renderer-only endpoints such as settings form state, graph summaries, token summaries, and vault assets are internal to the desktop product and should not be treated as stable integration points.

## Removed Low-Level Endpoints

Prototype connector, page-read, draft-write, scan, operation execution, old split workflow endpoints, and generic run-start endpoints are not public. Use `POST /ingest`, `POST /lint`, `POST /query`, and the run monitor endpoints above.

## Architecture Boundary

FastAPI is an adapter over Python Core. It should not own prompt contracts, model routing, page rendering rules, or vault policy. Those belong to the core, semantic, pipeline, storage, and runtime layers.
