# Testing And Quality Gates

This document lists the current test gates and their intended scope. The goal is
to keep local checks predictable without touching user runtime data.

## Default Change Validation

Start with the changed-file planner:

```bash
uv run python scripts/plan-affected-validation.py
```

In a dirty worktree containing more than one task, pass the exact task files so
unrelated changes do not inflate the plan:

```bash
uv run python scripts/plan-affected-validation.py --paths path/to/owner.py tests/test_owner.py
```

It reports a path-based risk floor, mechanically determinable commands, and the
remaining owner/direct-consumer test review. The risk floor can only be raised
after inspecting the actual public, persisted, semantic, lifecycle, packaging,
or release dependency closure. Run its mechanical subset with `--run`, then add
the focused tests required by that review.

R3 does not automatically require full unit discovery, `dev-check.sh`, desktop
packaging, or live-model tests. Those gates are selected only when the changed
dependency closure reaches them or work enters a release/full-acceptance node.

For an admitted Patterned Harness Initiative, the affected planner informs the
fixed Adapter Gate catalog but does not own completion. `pnpm harness --`
captures the baseline, executes the fixed integration checks, compares stable
Gate identities at acceptance, and enforces scope. Selected full-chain or
live-model evidence is represented by bounded receipts—never raw output. An
identical pre-existing
failure stays visible without being
attributed to the Initiative. A new or changed hard failure blocks acceptance;
a soft failure requires a recorded owner, acknowledgement, and expiry/removal
condition.

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
cd renderer
npm ci
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

Renderer output is local build output; do not commit
`renderer/node_modules/` or `renderer/dist/`.

## Broad Development Gate

```bash
scripts/dev-check.sh
```

Current scope:

- frontend build;
- frontend dependency audit;
- Playwright UI smoke;
- desktop type/build, update repository contracts, and production dependency audit;
- Python lint with Ruff;
- architecture dependency and cycle governance;
- documentation governance and local Markdown link checks;
- Python unit tests;
- CLI diagnostics against a temporary config and temporary vault;
- Python package build.

This script must not write to the maintainer's real `vaults/`, `config.yaml`, or
`.env`. It is a broad integration gate, not the default command for every local
change.

## Individual Quality Gates

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-architecture.py
uv run python scripts/check-doc-governance.py
uv run python scripts/check-doc-links.py
cd renderer && npm run check:i18n
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

The clean clone smoke test checks out the exact candidate commit and writes only
inside a temporary clone.

## Continuous Integration

Pushes and pull requests targeting `KnoArbor` run Python lint/tests,
architecture and documentation governance, renderer build/Playwright, desktop
contracts, and package build. A `knoarbor-v*` tag cannot build publishable
desktop artifacts until `release-check.sh` passes from that exact tag.

## Live Model Smoke

```bash
set -a && source .env && set +a
scripts/live-release-candidate-smoke.sh
```

Required environment variables are `KNOARBOR_LIVE_MODEL_API_KEY`,
`KNOARBOR_LIVE_MODEL_BASE_URL`, and `KNOARBOR_LIVE_MODEL_NAME`.

Scope:

- temporary Markdown ingest;
- temporary Codex-session ingest;
- structural lint;
- query;
- one Raw-grounded Chat answer with resolved citations;
- one verified no-match general answer with explicit provenance and no local citations;
- non-Markdown missing-preprocessor negative check.

This test calls a real model provider and is intentionally separate from the
default release gate. It must use a temporary vault and temporary config.

## Persistent Real-Document Benchmark

Real-document quality evaluation is opt-in and must use a dedicated local
benchmark vault plus a disposable execution vault. Keep source identities and
reviewed expected evidence stable, but never treat product-generated Raw,
projections, indexes, sessions, or reports as fixture authority.

Raw/span fidelity, wrong-vault leakage, unsupported grounded propositions, and
incorrect general-knowledge routing are hard failures. Report retrieval,
answer coverage, latency, tokens, and storage separately; an aggregate score
must not hide a critical failure. Private corpora and provider credentials are
never committed to the public repository.

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
