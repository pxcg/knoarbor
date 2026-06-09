# Development

## Setup

```bash
uv sync
```

Run the CLI:

```bash
uv run knoar --help
```

Run the API:

```bash
uv run knoar serve
```

## Tests

Run the current test suite:

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-doc-links.py
uv run --extra dev python -m unittest discover tests
```

Run the local development gate when preparing a release candidate:

```bash
scripts/dev-check.sh
```

The script runs frontend build, Ruff, documentation link checks, Python unit tests, read-only `doctor`, and Python package build in the required order. For final release candidates, run the full release gate:

```bash
scripts/release-check.sh
```

`release-check.sh` runs `dev-check.sh`, `release-readiness.py`, and `clean-clone-smoke.sh` in order. `dev-check.sh` includes frontend build, frontend dependency audit, Playwright UI smoke, Ruff, documentation link checks, Python tests, read-only `doctor`, and package build.

When a model provider is available, run the live release-candidate smoke test:

```bash
set -a && source .env && set +a
scripts/live-release-candidate-smoke.sh
```

This creates a temporary vault, runs Markdown ingest, Codex-session ingest,
structural lint, query, and a negative non-Markdown preprocessor check. The
temporary directory is removed automatically.

For the complete test matrix and release gate boundaries, see
[Testing And Quality Gates](TESTING.md).

If your environment blocks the default uv cache path, use a project-local cache:

```bash
UV_CACHE_DIR=.uv-cache uv run --extra dev python -m unittest discover tests
```

## Runtime Data Isolation

Test and release scripts must never operate on a maintainer's real runtime data by default.

User-owned runtime data includes:

- `config.yaml` and `.env` in the project root.
- The project-root `wiki/` runtime vault.
- Connector source directories such as local chat sessions, Markdown note folders, raw document folders, or private export directories.
- Any local workflow export, cache, or private development record that is ignored by git.

Required rule:

- Automated gates may read `config.example.yaml`, but they must write a temporary config when a command needs configuration.
- Automated gates that need a vault must create one under `mktemp -d` and remove it with `trap` cleanup.
- Automated gates must not initialize, rewrite, lint, ingest, or clean the project-root `wiki/`, `config.yaml`, or `.env`.
- Only explicit user-facing product commands, such as `knoar init`, `knoar ingest`, API calls, or UI actions, may operate on the configured real vault.
- Repository scripts must not use broad cleanup commands such as `git clean -fdx` or `rm -rf` against ignored project-root runtime paths.

Safe script pattern:

```bash
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEMP_CONFIG="$TMP_DIR/config.yaml"
TEMP_VAULT="$TMP_DIR/wiki"

# Copy config.example.yaml into TEMP_CONFIG, rewrite vault.path to TEMP_VAULT,
# then run CLI/API checks against TEMP_CONFIG only.
```

The only intentional tracked generated path is `src/knoarbor/ui/dist/`, because it is bundled into the Python package. All runtime vault content remains local user data.

## Web Console

The web console is bundled into the Python package, but it is not published as a standalone npm package.

Frontend source lives in `web/`. Build it manually when the UI changes:

```bash
cd web
npm install
npm run build
```

The generated static files are copied into `src/knoarbor/ui/dist/` so `uv run knoar serve` can serve the console at `/`, with `/ui` kept as a compatibility alias.

Do not commit `web/node_modules/`, `web/dist/`, or local TypeScript build cache files.

Run the browser smoke test when changing console navigation, layout, or API wiring:

```bash
cd web
npx playwright install chromium
npm run test:e2e
```

The Playwright web server starts the packaged FastAPI app on a temporary local port and opens the bundled management console, so it validates the same route shape used by `knoar serve`.

## Package Build

Build the Python package before release candidates:

```bash
uv build
```

These are the current required gates: Python unit tests, Ruff, documentation link checks, frontend build, frontend dependency audit, Playwright UI smoke, read-only `doctor`, and package build. Type checks and frontend linting are target gates and should not be treated as required until the tools are configured in the repository and CI.

When running checks in the same working tree, run them sequentially. The frontend build rewrites `src/knoarbor/ui/dist/`, while Python UI tests read that directory.

Additional release helpers:

```bash
scripts/prepare-release.py 0.5.2
scripts/release-readiness.py
scripts/clean-clone-smoke.sh
scripts/release-check.sh
```

`prepare-release.py` synchronizes package metadata and creates release note placeholders. Run it from a clean tree before curating `CHANGELOG.md` and `docs/releases/<version>.md`. `release-readiness.py` checks branch, dirty tree state, required public files, and tracked private runtime paths. `clean-clone-smoke.sh` clones the local repository into a temporary directory and verifies install, frontend build, Python tests, read-only `doctor`, package build, and basic CLI commands without model API calls. `release-check.sh` runs the complete local release gate sequence.

`live-release-candidate-smoke.sh` is intentionally separate from
`release-check.sh` because it calls a real model provider and requires
`DEEPSEEK_API_KEY`.

## Branch And Release Model

KnoArbor uses a small release-oriented branch model. The goal is to keep public
history easy to understand while still allowing active development.

Branch roles:

- `main`: public release branch. It should always represent the latest public
  release line or a release-ready documentation update. It must stay buildable,
  documented, and suitable for tagging.
- `dev`: daily integration branch for the next minor or patch release. Feature
  work is merged here first. `dev` may move faster than `main`, but it should
  still pass the normal development gate before being pushed.
- `feature/*`: focused product or architecture work branched from `dev`.
- `fix/*`: focused bug fixes branched from `dev`, or from `main` only for an
  urgent public hotfix.
- `docs/*`: documentation-only work branched from `dev`, unless it fixes public
  release documentation on `main`.
- `release/*`: optional short-lived release-candidate stabilization branches
  created from `dev` when a release needs more than one validation pass.

Daily development flow:

1. Start new work from `dev`, not from `main`.
2. Use a focused branch name, such as `feature/source-segmentation` or
   `fix/query-context-pack`.
3. Keep commits scoped to one architectural or user-facing concern.
4. Run the relevant local checks before merging into `dev`.
5. Merge or fast-forward into `dev`; do not tag from `dev`.

Release flow:

1. Finish and test changes on `dev`.
2. Freeze `dev` for a release candidate. If stabilization needs multiple
   commits, create `release/vX.Y.Z` from `dev`.
3. Run Python tests, frontend build, frontend dependency audit, Playwright UI
   smoke, package build, clean-clone smoke checks, and any available live-model
   smoke test.
4. Run `scripts/prepare-release.py <version>`, then curate `CHANGELOG.md` and
   `docs/releases/v<version>.md`.
5. Merge or fast-forward the release candidate into `main`.
6. Tag the release from `main` only, for example `v1.1.0`.
7. Publish package artifacts only after the `main` tag exists.
8. Merge `main` back into `dev` if release notes, version metadata, or hotfixes
   changed on `main`.

Hotfix flow:

1. Branch `fix/<issue>` from `main` only when the released version needs an
   urgent patch.
2. Keep the change minimal and run the release gate appropriate for the touched
   area.
3. Merge into `main`, tag a patch release, then merge `main` back into `dev`.

Hard rules:

- Do not tag releases from `dev`, feature branches, or a dirty working tree.
- Do not push runtime vault data, private config, `.env`, local workflow exports,
  or maintainer-only notes to any public branch.
- Do not rewrite public release tags after they have been announced, except to
  correct a release process failure before users have consumed the artifact.
- Do not use `main` as the normal daily development branch after `dev` exists.

## Spec-Driven Development Flow

Use [`specs/`](../specs/README.md) for changes that are larger than an isolated
fix. A feature spec is required when the change affects public contracts,
architecture boundaries, source connectors, semantic contracts, workflow
behavior, autonomous maintenance, or release-critical user experience.

Recommended flow:

1. Start from the roadmap theme or user problem.
2. Create or update `specs/<feature>/requirements.md`.
3. Define owning layers, contracts, data flow, and rejected alternatives in
   `specs/<feature>/design.md`.
4. Track implementation status in `specs/<feature>/tasks.md`.
5. Define automated and manual checks in `specs/<feature>/verification.md`.
6. Implement code and tests against the spec.
7. Promote stable user-facing behavior into `docs/` and release notes.

Specs are not a second roadmap and should not duplicate long-term docs. They
are the implementation bridge between `docs/ROADMAP.md`, architecture
boundaries, code, and verification.

Conformance rule:

- `requirements.md` owns what must be true for users.
- `design.md` owns where the behavior belongs and which alternatives were
  rejected.
- `tasks.md` owns current implementation status.
- `verification.md` owns the checks required before the work is considered
  complete.

Code should be placed in the layer named by the spec design. If implementation
requires a different layer boundary than the spec described, update the spec in
the same change instead of adding a local workaround.

## Package Layout

```text
src/knoarbor/
├── core/          # schemas, config, hashing, redaction, shared rules
├── connectors/    # source adapters
├── pipelines/     # ingest, lint, query, write orchestration
├── semantic/      # prompt contracts, model client, semantic workflows
├── storage/       # vault, paths, index, ledger, writer
├── audit/         # reports, ledgers, query records
├── maintenance/   # lint scanner and wiki operations
├── retrieval/     # markdown and link retrieval
├── presenters/    # context pack formatting
├── services/      # API service adapters
└── entrypoints/   # FastAPI routes
```

## Design Rules

Project-specific engineering planning notes are kept outside public release archives. Public contributions should follow this document, [CONTRIBUTING.md](../CONTRIBUTING.md), and the architecture boundaries in [ARCHITECTURE.md](ARCHITECTURE.md).

Short version:

- Keep Python Core independent from host AI tools, external workflow adapters, and individual connectors.
- Keep connectors source-specific, but convert outputs to shared source contracts.
- Keep semantic contracts explicit: prompt + JSON schema + Pydantic validation.
- Keep vault writes centralized in storage/write pipelines.
- Prefer root-cause and architecture fixes over local fallback patches.
- Do not add fallback behavior unless it has been reviewed as a long-term reliability mechanism.
- Do not commit runtime wiki data, private raw sources, or model credentials.

## Connector Development Checklist

Adding a source connector is a source-layer change. Use the active
[1.3 Source Ecosystem spec](../specs/1.3-source-ecosystem/requirements.md)
when the connector changes public capability metadata or source behavior.

Checklist:

1. Implement `discover`, `fetch`, and `to_document` behind the `SourceConnector`
   protocol.
2. Register the connector in `connectors/registry.py`.
3. Declare capability metadata through `capabilities()` or default capability
   inference:
   - connector name and version;
   - emitted `source_types`;
   - `settings_schema`;
   - checkpoint, segmentation hint, and external-service flags.
4. Keep source-specific parsing inside the connector. Do not add connector
   branches to ingest semantic prompts, page writers, or API routes.
5. Emit normalized `SourceDocument` values before checkpointing, segmentation,
   relation planning, or drafting.
6. Add connector tests for discovery, normalization, capability metadata, and
   malformed input.
7. Update API/CLI/config docs only when the public connector surface changes.

Before merging connector work, run at least:

```bash
uv run python -m unittest tests.test_connector_contracts tests.test_source_pipeline tests.test_cli tests.test_api_surface
uv run python scripts/check-doc-links.py
```

## Frontend Design Baseline

KnoArbor's console should feel like a mature knowledge workbench, not a decorative landing page or a raw admin console.

UI contributions should follow these rules:

- Keep the interface quiet, dense enough for repeated work, and visually stable during long-running workflows.
- Prefer white surfaces, restrained green accents, thin borders, and compact type over large marketing-style panels.
- Use cards for discrete repeated objects, reports, run records, source records, and page previews. Avoid nested decorative cards.
- Keep page headers compact. Primary workflow content should appear above diagnostics and history where possible.
- Avoid radial glow backgrounds, decorative orbs, one-color gradient themes, and oversized hero typography.
- Use real screenshots or Playwright smoke checks after layout changes. Check at least overview, runs, sources, wiki, reports, and settings when touching global CSS.
- Do not expose internal status codes as primary UI text. Map them to user-facing labels and keep raw values in details or reports.
- Keep icons functional and consistent. Icons should support scanning; they should not replace essential labels unless the sidebar is collapsed.

## Release Notes

Internal modification notes live outside the tracked source tree in `.local-dev/`. Public release notes should be curated separately before publishing a release.
