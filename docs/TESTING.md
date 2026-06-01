# Testing And Quality Gates

This document lists the current test gates and their intended scope. The goal is
to keep local checks predictable without touching user runtime data.

## Local Unit Tests

```bash
uv run python -m unittest discover -s tests
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
npm run build
npm run test:e2e
```

Scope:

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
- Python unit tests;
- CLI diagnostics against a temporary config and temporary vault;
- Python package build.

This script must not write to the maintainer's real `wiki/`, `config.yaml`, or
`.env`.

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

- Python linting with a configured rule set.
- Static type checks for selected Python modules.
- Frontend linting.
- API schema snapshot tests.
- Longer live model regression fixtures.

Do not document these as required until the tools and CI jobs exist.
