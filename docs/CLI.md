# CLI Reference

The recommended short command is:

```bash
uv run knoar --help
```

The full command remains available for compatibility:

```bash
uv run knoarbor --help
```

## Global Options

```bash
uv run knoar --config ./config.yaml <command>
```

If `--config` is omitted, the CLI searches for `config.yaml` and falls back to
`config.example.yaml`.

## Recommended Commands

These commands mirror the stable API surface: `/ingest`, `/lint`, `/query`,
`/runs`, `/wiki/pages`, `/doctor`, and `/health`.

### `first-run`

Create a local `config.yaml` when missing, initialize the vault, and run
read-only diagnostics.

```bash
uv run knoar first-run
uv run knoar first-run --vault ./vaults/default
uv run knoar first-run --no-example
uv run knoar first-run --json
```

This command does not call the model and does not write wiki pages. It prepares
the local runtime and prints the next recommended commands. By default it copies
a small bundled Markdown example to `raw/inbox/notes/agent-loop.md`, so a new user can
test the first page flow with:

```bash
uv run knoar ingest --connector markdown --write
uv run knoar query "Agent Loop 是什么？"
```

### `init`

Initialize a runtime wiki vault.

```bash
uv run knoar init --vault ./vaults/default
```

When `config.yaml` is missing, `init` creates one from the bundled default
configuration before initializing the vault. Existing local config files are not
overwritten.

### `serve`

Start the local FastAPI service and management UI.

```bash
uv run knoar serve
```

If the configured port is already in use, KnoArbor automatically switches to the
next available local port and prints the actual UI/API address. The runtime
endpoint is also written to `.knoarbor/endpoint.json` next to `config.yaml` so
local integrations can discover the active service. A user-level endpoint is
also written to `~/.knoarbor/endpoint.json`, so host-AI skills can discover the
service without running from the project directory.

Override host and port:

```bash
uv run knoar serve --host 0.0.0.0 --port 8000
```

### `status`

Print a local vault summary.

```bash
uv run knoar status --vault ./vaults/default
uv run knoar status --vault-id personal
```

### `vaults`

List configured knowledge-base vaults. Use this before choosing a `--vault-id`
for ingest, lint, query, reports, pages, or run inspection.

```bash
uv run knoar vaults
uv run knoar vaults list
uv run knoar vaults --json
```

The output marks the active default vault with `*` and reports whether each
configured path is available.

### `doctor`

Run read-only first-run diagnostics. This checks config loading, vault
initialization files, default model provider settings, API key environment
variables, connector discovery, optional document preprocessing settings, and
recent run state. It does not call the model and does not write wiki pages.

```bash
uv run knoar doctor
uv run knoar doctor --connector markdown
uv run knoar doctor --json
```

### `sources`

Normalize source documents from enabled connectors without running semantic
ingest.

```bash
uv run knoar sources
uv run knoar sources --catalog
uv run knoar sources --connector markdown
uv run knoar sources --connector codex --json
uv run knoar sources --connector codex --json --include-content
```

Use `--catalog` to print the connector capability catalog without scanning
local files. This shows connector names, versions, emitted `source_type` values,
whether checkpointing or segmentation hints are supported, and the lightweight
settings schema for JSON output.

`sources --json` prints compact preflight metadata by default. Use
`--include-content` only when you intentionally need the full normalized
`SourceDocument.content` payload.

### `desktop-config`

Read and write desktop configuration payloads without starting the HTTP server.
This command is used by the Electron desktop shell and is also useful for local
diagnostics.

```bash
uv run knoar desktop-config read-form --json
uv run knoar desktop-config diagnostics --refresh-source-counts --json
uv run knoar desktop-config write-form --input payload.json --json
```

### `ingest`

Run the unified ingest workflow.

Connector-based ingest:

```bash
uv run knoar ingest --write
uv run knoar ingest --connector markdown --write
uv run knoar ingest --vault-id personal --connector markdown --write
```

One-off file or folder ingest. Markdown files run directly; non-Markdown files
require the configured MinerU-compatible preprocessor:

```bash
uv run knoar ingest --input /path/to/note.md --write
uv run knoar ingest --input /path/to/paper.pdf --write
uv run knoar ingest --input /path/to/folder --write
uv run knoar ingest --input /path/to/paper.pdf --write --no-follow
```

Ingest uses one semantic extraction path. Short inputs normally use one model
call; long inputs are split by the configured character budgets and merged at
the source/window boundary. The resulting factual revision is published
atomically, then readable source and machine-index projections are materialized.

When `--input` is a folder, KnoArbor discovers Markdown files recursively by
default. Rich files in that folder are first converted through the configured
MinerU-compatible preprocessor.

Prepared source document ingest:

```bash
uv run knoar ingest --source-document /path/to/source_document.json --write
```

Recovery from a failed or partially failed ingest run:

```bash
uv run knoar ingest --recover-run-id RUN_ID --write
uv run knoar ingest --vault-id personal --recover-run-id RUN_ID --write
```

Rebuild deterministic source projections and the machine index without rerunning model extraction:

```bash
uv run knoar ingest --rebuild-materialization
```

`ingest` executes its persisted task in the CLI process and returns after the
local operation finishes. Human-readable output prints progress events and
heartbeat lines. Use `--json` for a pure machine-readable response, or
`--no-follow` to print only the final summary; neither option changes execution ownership.

When multiple vaults are configured, ingest writes to one vault per command. Use
`--vault-id <id>` to select a configured vault, or `--vault /path/to/vault` for an
explicit vault path.

### `lint`

Run the unified lint maintenance workflow.

```bash
uv run knoar lint
uv run knoar lint --vault-id personal
uv run knoar lint --mode deterministic
uv run knoar lint --mode semantic
uv run knoar lint --mode semantic
```

Modes:

- `deterministic`: scan, execute deterministic owner-routed repairs, and rescan.
- `semantic`: add evidence-bound semantic diagnosis and automatically reingest sources whose approved findings concern canonical knowledge quality.

Semantic models emit findings rather than replacement knowledge. Lint executes
the resulting repair plan through ingest or materialization automatically.

Like ingest, `lint` follows progress by default for human-readable output. Use
`--json` for machine-readable output or `--no-follow` for synchronous summary
output.

When multiple vaults are configured, lint maintains one vault per command. Use
`--vault-id <id>` to select a configured vault, or `--vault /path/to/vault` for an
explicit vault path.

### `query`

Retrieve KnoArbor context for a question. The CLI returns context; it does not
generate a final answer.

```bash
uv run knoar query "Agent Loop 和控制模式是什么？"
uv run knoar query "RAG 和 LLM-Wiki 的区别"
uv run knoar query --vault-id personal "Agent Loop 是什么？"
```

Query uses one semantic atom-to-claim-to-raw strategy and returns the complete
matched evidence set. Recall breadth follows the semantic query and evidence
sufficiency.

The returned context pack keeps one optional projection-locator list separate
from claim-backed raw evidence. Raw evidence/source units are the only factual
material. Use `pages read` when a caller needs a projection body for navigation
or inspection.

Use `--json` when another tool or skill needs structured fields. Use
`--write-report` when you want the query run to leave an audit artifact under
`maintenance/reports/query/query_report_*.md`.

### `query-feedback`

Record relevance feedback for a previous query. Feedback is stored in the query
feedback ledger and is used for later retrieval diagnostics.

```bash
uv run knoar query-feedback "Agent Loop 是什么？" --useful --selected-path Agent-Loop.md
uv run knoar query-feedback "Agent Loop 是什么？" --no-useful --rejected-path Old-Page.md
```

### `pages`

List, read, or inspect generated wiki pages.

```bash
uv run knoar pages list
uv run knoar pages list --dir pages
uv run knoar pages list --contains "Agent Loop"
uv run knoar pages read Agent-Loop-and-Control-Patterns.md
uv run knoar pages relations Agent-Loop-and-Control-Patterns.md
uv run knoar pages read --vault-id personal Agent-Loop-and-Control-Patterns.md
```

Use `pages read` after query when you need the full maintained page body. Use
`pages relations` to inspect page relation metadata without opening the UI.

Page paths are relative to the maintained content root. In the default layout,
KnoArbor stores authored pages and deterministic source projections under
`vaults/default/wiki/pages/`, using flat paths such as `Agent-Loop.md`.
Legacy vaults may still expose historical `sources/...` pages.

### `vaults`

List configured knowledge bases.

```bash
uv run knoar vaults list
```

### `reports`

List or read workflow reports from the selected vault.

```bash
uv run knoar reports list
uv run knoar reports read maintenance/reports/ingest/ingest_report_YYYYMMDD_HHMMSS.md
uv run knoar reports list --vault-id personal
```

Use reports after ingest, lint, or query runs to inspect written pages, applied
maintenance operations, failures, token usage, and run metrics.

### `runs`

List recent or active workflow runs from the local run monitor.

```bash
uv run knoar runs
uv run knoar runs list
uv run knoar runs --active
uv run knoar runs --json
```

### `runs events`

Show the event log for one workflow run. Use `--follow` for a terminal-style
progress stream.

```bash
uv run knoar runs events RUN_ID
uv run knoar runs events RUN_ID --follow
```

### `runs cancel`

Request cooperative cancellation for an active run.

```bash
uv run knoar runs cancel RUN_ID
```

### `scan`

Run deterministic scan without writing a maintenance report.

```bash
uv run knoar scan --vault ./vaults/default
```

## Developer Diagnostics

These commands are intended for prompt/schema debugging, not ordinary use.

### `lint-plan`

Run semantic lint diagnosis and review without writing changes.

```bash
uv run knoar lint-plan --mode deterministic
uv run knoar lint-plan --mode semantic --json
```

### `contracts`

List semantic contracts.

```bash
uv run knoar contracts
```

### `run-contract`

Run one semantic contract with a JSON payload.

```bash
uv run knoar run-contract index_metadata_extract --input /path/to/input.json
```
