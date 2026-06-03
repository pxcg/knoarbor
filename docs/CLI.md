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
uv run knoar first-run --vault ./wiki
uv run knoar first-run --no-example
uv run knoar first-run --json
```

This command does not call the model and does not write wiki pages. It prepares
the local runtime and prints the next recommended commands. By default it copies
a small bundled Markdown example to `raw/notes/agent-loop.md`, so a new user can
test the first page flow with:

```bash
uv run knoar ingest --connector markdown --write
uv run knoar query "Agent Loop 是什么？"
```

### `init`

Initialize a runtime wiki vault.

```bash
uv run knoar init --vault ./wiki
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
local integrations can discover the active service.

Override host and port:

```bash
uv run knoar serve --host 0.0.0.0 --port 8000
```

### `status`

Print a local vault summary.

```bash
uv run knoar status --vault ./wiki
```

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
uv run knoar sources --connector markdown
uv run knoar sources --connector codex --json
uv run knoar sources --connector codex --json --include-content
```

`sources --json` prints compact preflight metadata by default. Use
`--include-content` only when you intentionally need the full normalized
`SourceDocument.content` payload.

### `ingest`

Run the unified ingest workflow.

Connector-based ingest:

```bash
uv run knoar ingest --write
uv run knoar ingest --connector markdown --write
```

Single file ingest. Markdown files run directly; non-Markdown files require the
configured MinerU-compatible preprocessor:

```bash
uv run knoar ingest --input /path/to/note.md --write
uv run knoar ingest --input /path/to/paper.pdf --write
uv run knoar ingest --input /path/to/paper.pdf --write --no-follow
```

Prepared source document ingest:

```bash
uv run knoar ingest --source-document /path/to/source_document.json --write
```

Recovery from a failed or partially failed ingest run:

```bash
uv run knoar ingest --recover-run-id RUN_ID --write
```

`ingest` is a long-running command. Human-readable CLI output follows the local
run queue by default and prints progress events plus heartbeat lines. Use
`--json` for a pure machine-readable response, or `--no-follow` when you
explicitly want synchronous summary output.

### `lint`

Run the unified lint maintenance workflow.

```bash
uv run knoar lint
uv run knoar lint --mode deterministic
uv run knoar lint --mode structural
uv run knoar lint --mode quality
uv run knoar lint --mode full --profile deep
uv run knoar lint --mode full --apply-reviewed
```

Modes:

- `deterministic`: scan and apply deterministic safe fixes only.
- `structural`: structural/provenance maintenance with semantic review when needed.
- `quality`: page quality diagnosis and reviewed maintenance.
- `full`: structural plus quality maintenance.

`--profile standard|deep` controls audit budget only. `deep` keeps the same lint
contract but reads more page context and returns more candidates for scheduled or
occasional deep audits.

Like ingest, `lint` follows progress by default for human-readable output. Use
`--json` for machine-readable output or `--no-follow` for synchronous summary
output.

### `query`

Retrieve KnoArbor context for a question. The CLI returns context; it does not
generate a final answer.

```bash
uv run knoar query "Agent Loop 和控制模式是什么？"
uv run knoar query --mode deep --max-results 8 "RAG 和 LLM-Wiki 的区别"
uv run knoar query --context-format full "Agent Loop 和控制模式是什么？"
```

Modes:

- `quick`: compact routing context, no excerpts.
- `balanced`: default evidence bundle with bounded excerpts and related-page expansion.
- `deep`: larger local evidence budget, still retrieval-only.

Context format:

- `compact`: default bounded context pack for host AI tools.
- `full`: returns complete matched wiki page bodies in the context pack.

Use `--json` when another tool or skill needs structured fields. Use
`--write-report` when you want the query run to leave an audit artifact under
`maintenance/query_report_*.md`.

### `query-feedback`

Record relevance feedback for a previous query. Feedback is stored in the query
feedback ledger and is used for later retrieval diagnostics.

```bash
uv run knoar query-feedback "Agent Loop 是什么？" --useful --selected-path concepts/Agent-Loop.md
uv run knoar query-feedback "Agent Loop 是什么？" --no-useful --rejected-path concepts/Old-Page.md
```

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
uv run knoar scan --vault ./wiki
```

## Developer Diagnostics

These commands are intended for prompt/schema debugging, not ordinary use.

### `lint-plan`

Run semantic lint diagnosis and review without writing changes.

```bash
uv run knoar lint-plan --mode structural
uv run knoar lint-plan --mode quality --json
```

### `contracts`

List semantic contracts.

```bash
uv run knoar contracts
```

### `run-contract`

Run one semantic contract with a JSON payload.

```bash
uv run knoar run-contract source_normalize --input /path/to/input.json
```
