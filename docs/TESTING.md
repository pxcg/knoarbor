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
- navigation smoke against the packaged developer console;
- basic UI/API wiring.

During the desktop-first transition, the renderer is still copied into
`src/knoarbor/ui/dist/` for developer-console smoke tests; do not commit
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
