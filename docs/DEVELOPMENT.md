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

```bash
uv run python scripts/plan-affected-validation.py
```

Use `--run` for the mechanically selected subset, then add focused owner and
direct-consumer tests from the actual dependency closure. `scripts/dev-check.sh`
is a broad integration/release checkpoint, not the default for every change.
The command and test taxonomy are owned by
[Testing And Quality Gates](TESTING.md). Release decisions use the
[Release Checklist](RELEASE_CHECKLIST.md). This document does not duplicate
their individual gates.

If your environment blocks the default uv cache path, use a project-local cache:

```bash
UV_CACHE_DIR=.uv-cache uv run --extra dev python -m unittest discover tests
```

## Runtime Data Isolation

Test and release scripts must never operate on a maintainer's real runtime data by default.

User-owned runtime data includes:

- `config.yaml` and `.env` in the project root.
- The project-root `vaults/` runtime vault.
- Connector source directories such as local chat sessions, Markdown note folders, raw document folders, or private export directories.
- Any local workflow export, cache, or private development record that is ignored by git.

Required rule:

- Automated gates may read `config.example.yaml`, but they must write a temporary config when a command needs configuration.
- Automated gates that need a vault must create one under `mktemp -d` and remove it with `trap` cleanup.
- Automated gates must not initialize, rewrite, lint, ingest, or clean the project-root `vaults/`, `config.yaml`, or `.env`.
- Only explicit user-facing product commands, such as `knoar init`, `knoar ingest`, API calls, or UI actions, may operate on the configured real vault.
- Repository scripts must not use broad cleanup commands such as `git clean -fdx` or `rm -rf` against ignored project-root runtime paths.

Safe script pattern:

```bash
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEMP_CONFIG="$TMP_DIR/config.yaml"
TEMP_VAULT="$TMP_DIR/vault"

# Copy config.example.yaml into TEMP_CONFIG, rewrite vault.path to TEMP_VAULT,
# then run CLI/API checks against TEMP_CONFIG only.
```

Renderer build output lives in the ignored local directory `renderer/dist`. All runtime vault content remains local user data.

## Web Console

The renderer is built from `renderer/` and is not published as a standalone npm package.

Renderer source lives in `renderer/`. Build it manually when the UI changes:

```bash
cd renderer
npm install
npm run build
```

The generated static files stay in `renderer/dist`; desktop packaging reads that directory directly.

Do not commit `renderer/node_modules/`, `renderer/dist/`, or local TypeScript build cache files.

Run the browser smoke test when changing console navigation, layout, or API wiring:

```bash
cd renderer
npx playwright install chromium
npm run test:e2e
```

The Playwright web server starts the packaged FastAPI app on a temporary local port and opens the bundled management console, so it validates the same route shape used by `knoar serve`.

## Development Method

Material changes use the lightest valid SDD level described in
[`specs/README.md`](../specs/README.md): identify the accepted owner, update the
specification before changing cross-layer contracts, implement at the owning
boundary, and close with tests, documentation, and coherent commits.

`integrations/skills` contains distributable host-AI integration skills only.

## Desktop Build

Install both frontend workspaces before the first desktop build:

```bash
cd renderer && npm install && cd ..
cd desktop && npm install && cd ..
```

Before packaging or installation, inventory installed copies, running
processes, user data, external vaults, and build residue. Keep build cleanup,
application replacement, local-data reset, and external-vault deletion as
separate explicitly selected operations.

After that inventory, an unpacked macOS application is built from the repository root with:

```bash
npm run pack:mac
```

The desktop package command is self-contained: it removes previous generated
package artifacts, then rebuilds the renderer, bundled Python service, Electron
main process, and preload before invoking the packager. Generated output remains
under ignored build directories; it is never committed. Packaging never implies
data deletion or installation, and only one explicitly verified
`/Applications/KnoArbor.app` may be installed.

## Package Build

Build the Python package before release candidates:

```bash
uv build
```

Release helpers and their required order are documented in
[Testing And Quality Gates](TESTING.md) and
[Release Checklist](RELEASE_CHECKLIST.md).

## Branch And Release Model

`KnoArbor` is the active integration and release branch of the company
repository. Legacy `origin/main` and `origin/dev` retain upstream history but
are not the default targets for current KnoArbor development.

- Start focused work from `KnoArbor` and use `codex/*`, `feature/*`, `fix/*`, or
  `docs/*` branches when isolation is needed.
- Keep commits scoped to one owner or user-visible concern and merge them back
  into `KnoArbor` only after affected validation passes.
- Create production tags from a clean `KnoArbor` checkout using the
  `knoarbor-vX.Y.Z` namespace.
- For a release candidate, run `scripts/release-check.sh`, prepare the changelog
  and `docs/releases/vX.Y.Z.md`, then build/sign/package through the desktop
  lifecycle and release procedures.
- Urgent fixes branch from the released `KnoArbor` commit and return to
  `KnoArbor` after the patch release.

Do not rewrite consumed release tags or push runtime vaults, private config,
`.env`, local workflow exports, or maintainer-only notes. A dirty working tree
is never a release source.

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
├── pipelines/     # ingest, lint, and query orchestration
├── semantic/      # prompt contracts, model client, semantic workflows
├── storage/       # vault, immutable facts, indexes, and materialization
├── audit/         # reports, ledgers, query records
├── maintenance/   # lint scanners and maintenance analysis
├── retrieval/     # knowledge and page retrieval
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
- Keep factual writes centralized in source revisions and SQLite source-head
  publication; keep user-visible wiki pages in the materialization layer.
- Prefer root-cause and architecture fixes over local fallback patches.
- Run `uv run python scripts/check-architecture.py` when changing module ownership or cross-layer imports.
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
5. Emit normalized `SourceDocument` values before immutable input admission,
   segmentation, semantic extraction, or factual publication.
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
