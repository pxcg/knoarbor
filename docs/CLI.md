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

If `--config` is omitted, the CLI searches for `config.yaml` and falls back to `config.example.yaml`.

## Commands

### `init`

Initialize a runtime wiki vault.

```bash
uv run knoar init --vault ./wiki
```

### `serve`

Start the local FastAPI service.

```bash
uv run knoar serve
```

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

Normalize source documents from enabled connectors.

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

Run connector-based ingest.

```bash
uv run knoar ingest --write
uv run knoar ingest --connector markdown --write
```

`ingest` is a long-running command. Human-readable CLI output follows the
local run queue by default and prints progress events plus heartbeat lines.
Use `--json` for a pure machine-readable response, or `--no-follow` when you
explicitly want synchronous summary output.

### `ingest-document`

Run semantic ingest for one prepared `source_document.v1` JSON file.

```bash
uv run knoar ingest-document --input /path/to/source_document.json --write
```

### `ingest-file`

`ingest-file` also follows progress by default for human-readable output:

```bash
uv run knoar ingest-file --input /path/to/paper.pdf --write
uv run knoar ingest-file --input /path/to/paper.pdf --write --no-follow
```

### `query`

Retrieve KnoArbor context for a question. The CLI returns context; it does not generate a final answer.

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
- `full`: returns complete matched wiki page bodies in the context pack. Use it when the caller wants raw maintained wiki text and can handle the larger response.

Use `--json` when another tool or skill needs the structured fields, including `match_kind`, `answer_guidance`, `gap_suggestions`, and `trace`. `match_kind` describes retrieval origin only: `direct` matched the query in the initial search scope, while `related` was reached through wiki links from a direct match. If page directories are filtered, related expansion can still cross directories unless disabled.

Use `--write-report` when you want the query run to leave an audit artifact under `maintenance/query_report_*.md`:

```bash
uv run knoar query --write-report "Agent Loop 是什么？"
```

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
uv run knoar runs --active
uv run knoar runs --json
```

### `run-events`

Show the event log for one workflow run. Use `--follow` for a terminal-style
progress stream.

```bash
uv run knoar run-events RUN_ID
uv run knoar run-events RUN_ID --follow
```

### `run-cancel`

Request cooperative cancellation for an active run.

```bash
uv run knoar run-cancel RUN_ID
```

### `run-rerun-failed`

Start a recovery ingest run from a failed or partially failed ingest run.

```bash
uv run knoar run-rerun-failed RUN_ID --write
```

### `scan`

Run deterministic scan without writing a maintenance report.

```bash
uv run knoar scan --vault ./wiki
```

### `lint`

Run deterministic lint and optionally write a report.

```bash
uv run knoar lint --vault ./wiki
uv run knoar lint --apply-safe-fixes
```

### `lint-run`

Run the unified lint maintenance contract.

```bash
uv run knoar lint-run
uv run knoar lint-run --mode structural
uv run knoar lint-run --mode quality
uv run knoar lint-run --mode full --profile deep
uv run knoar lint-run --mode full --apply-reviewed
```

`--profile standard|deep` controls audit budget only. `deep` keeps the same
lint contract but reads more page context and returns more candidates for
scheduled or occasional deep audits.

Like ingest, `lint-run` follows progress by default for human-readable output.
Use `--json` for machine-readable output or `--no-follow` for synchronous
summary output.

### `lint-plan`

Run semantic lint diagnosis and review without writing changes. This is a
diagnostic command for prompt/schema behavior and maintenance planning.

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

Run one semantic contract with a JSON payload. This is for debugging prompt/schema behavior.

```bash
uv run knoar run-contract source_normalize --input /path/to/input.json
```
