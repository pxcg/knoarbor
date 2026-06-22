# Testing And Quality Gates

This document lists the current test gates and their intended scope. The goal is
to keep local checks predictable without touching user runtime data.

## Local Unit Tests

```bash
uv run --extra dev python -m unittest discover -s tests
```

Scope:

- core schemas and config;
- connectors and source normalization;
- ingest, lint, query pipeline behavior;
- storage, index, and report utilities;
- API route contracts where covered by unit tests.

Unit tests must not require real model provider credentials.

## Frontend Build And UI Smoke

```bash
cd web
npm install
npm run check:i18n
npm run build
npm run test:e2e
```

Scope:

- Chinese/English UI translation key parity;
- TypeScript build;
- Vite production bundle;
- navigation smoke against the packaged FastAPI console;
- basic UI/API wiring.

The frontend is bundled into `src/knoarbor/ui/dist/`; do not commit
`web/node_modules/` or `web/dist/`.

## Development Gate

```bash
scripts/dev-check.sh
```

Current scope:

- frontend build;
- frontend dependency audit;
- Playwright UI smoke;
- Python lint with Ruff;
- local Markdown documentation link check;
- Python unit tests;
- CLI diagnostics against a temporary config and temporary vault;
- Python package build.

This script must not write to the maintainer's real `vaults/`, `config.yaml`, or
`.env`.

## Individual Quality Gates

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-doc-links.py
cd web && npm run check:i18n
```

These checks are part of `scripts/dev-check.sh` and CI. Run them directly when
iterating on Python code or public documentation.

## Test Taxonomy

KnoArbor keeps fast local checks separate from live-provider checks:

- **Unit tests** cover pure functions, schemas, retrieval scoring, report
  rendering, and pipeline policies with no network or user vault access.
- **Contract tests** cover API, CLI, skill helper, semantic schema, and model
  gateway boundaries with fake clients or temporary vaults.
- **Golden tests** lock representative ingest, lint, query, and semantic output
  shapes so user-facing reports and context packs do not drift silently.
- **UI smoke tests** cover page loading, navigation, and packaged console
  integration.
- **Live model smoke** is opt-in and uses temporary vaults only.

New tests should state which layer they protect. Real model tests must remain
outside the default local unit gate.

## Release Gate

```bash
scripts/release-check.sh
```

Current scope:

- development gate;
- release readiness checks;
- clean clone smoke test.

The clean clone smoke test writes only inside a temporary clone.

## Live Model Smoke

```bash
set -a && source .env && set +a
scripts/live-release-candidate-smoke.sh
```

Scope:

- temporary Markdown ingest;
- temporary Codex-session ingest;
- structural lint;
- query;
- non-Markdown missing-preprocessor negative check.

This test calls a real model provider and is intentionally separate from the
default release gate. It must use a temporary vault and temporary config.

## RAG Baseline Comparison

KnoArbor can be compared against conventional chunk retrieval with the same chat
fixture. The default local baseline does not start a database or external RAG
product. It reads the fixed Markdown source set, chunks it, runs BM25 retrieval,
and optionally calls a configured model to answer from the retrieved chunks. All
outputs are written under `tmp/rag-baselines/`.

This is a maintainer evaluation protocol, not part of the first-run user path.
New users can complete the product quickstart without running any comparison
benchmark.

The default comparison protocol uses:

- fixture: `tests/fixtures/chat/agent_architecture_6turn_mixed.json`;
- LLM-Wiki scope: `agent-engineering` vault;
- RAG-lite scope: `Agent.md`, `MCP.md`, and `OpenClaw架构.md`;
- output root: `tmp/eval-protocol/`.

Use `--rag-source-dir` when the three source notes live outside the default
local notes directory.

The second fixed fixture targets decision-oriented engineering synthesis:

- fixture: `tests/fixtures/chat/ios_audio_tennis_detection_6turn.json`;
- LLM-Wiki scope: `ios-audio-project` vault;
- RAG-lite scope: the raw files declared in the fixture under `rag_baseline.source_files`;
- evaluation goal: test whether wiki pages can organize a short iOS tennis
  audio request into model selection, data preparation, metrics, deployment,
  and MVP-to-production planning.

Larger raw-chat baselines are intentionally not built into a preset because
large chat logs can dominate chunk retrieval. Add those files explicitly with
`--file` or `--input-dir` when the evaluation goal requires them.

Dry-run the protocol before calling a real provider:

```bash
uv run python scripts/eval/llmwiki_rag_comparison.py --plan
```

Run one provider:

```bash
uv run python scripts/eval/llmwiki_rag_comparison.py \
  --run-rag \
  --run-llmwiki \
  --compare \
  --provider deepseek
```

Run the iOS audio fixture:

```bash
uv run python scripts/eval/llmwiki_rag_comparison.py \
  --fixture tests/fixtures/chat/ios_audio_tennis_detection_6turn.json \
  --run-rag \
  --run-llmwiki \
  --compare \
  --provider deepseek
```

```bash
uv run python scripts/eval/rag_lite_baseline.py --retrieval-only
```

To include a model answer:

```bash
uv run python scripts/eval/rag_lite_baseline.py --provider deepseek
```

The WeKnora baseline harness is still available when a WeKnora service is
already running and the goal is to compare against a full external RAG product.

```bash
uv run python scripts/eval/weknora_rag_baseline.py \
  --base-url http://127.0.0.1:8080 \
  --knowledge-base-id "$WEKNORA_KNOWLEDGE_BASE_ID"
```

To create a temporary WeKnora knowledge base and upload source files for a
baseline run:

```bash
uv run python scripts/eval/weknora_rag_baseline.py \
  --base-url http://127.0.0.1:8080 \
  --create-knowledge-base \
  --upload-dir /path/to/raw/agent-notes \
  --wait-processing
```

Credential options can be provided with `WEKNORA_API_KEY`,
`WEKNORA_BEARER_TOKEN`, or `WEKNORA_EMAIL` / `WEKNORA_PASSWORD`. This harness is
for evaluation only; it is not part of the KnoArbor runtime path.

## Manual Release Review

Before publishing a release, also follow
[Release Preflight Checklist](RELEASE_CHECKLIST.md). It covers privacy, license,
documentation, UI, API/CLI compatibility, and long-run safety.

## Target Future Gates

The following are desired but not yet required release gates:

- Static type checks for selected Python modules.
- Frontend linting.
- API schema snapshot tests.
- Longer live model regression fixtures.

Do not document these as required until the tools and CI jobs exist.
