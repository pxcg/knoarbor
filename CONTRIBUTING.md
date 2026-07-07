# Contributing

Thanks for considering a contribution to KnoArbor.

KnoArbor is a local-first knowledge pipeline. Contributions should preserve three boundaries:

- Connectors read sources and produce shared source contracts.
- Pipelines orchestrate ingest, lint, query, write, and maintenance.
- Semantic steps use explicit prompt contracts and validated JSON schemas.

Avoid adding hidden fallback behavior. If a reliability mechanism is needed, make it explicit in configuration, tests, reports, and documentation.

## Branch Model

- `main`: public release branch and release tag source.
- `dev`: daily integration branch for the next release.
- `feature/*`, `fix/*`, `docs/*`: focused short-lived branches from `dev`.

Open pull requests against `dev` unless maintainers request otherwise. Release changes are promoted from `dev` to `main`.

See [Development](docs/DEVELOPMENT.md#branch-and-release-model) for the full branch, release, and hotfix rules.

## Development Setup

```bash
uv sync
cp config.example.yaml config.yaml
cp config.example.yaml config.yaml
```

For semantic workflows, set at least one model provider `api_key` in
`config.yaml`, or use a local/private endpoint that does not require one.

## Tests

Run before opening a pull request:

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-doc-links.py
uv run --extra dev python -m unittest discover tests
```

If you change the web console:

```bash
cd web
npm install
npm run build
```

Build the package before release-oriented changes:

```bash
uv build
```

The web console is bundled into the Python package from `src/knoarbor/ui/dist/`. It is not published as a standalone npm package.

See [Testing And Quality Gates](docs/TESTING.md) for the full local gate matrix,
including release checks and live model smoke tests.

## Documentation

Update documentation when behavior changes:

- `README.md` for user-facing setup or project positioning.
- `docs/CONFIGURATION.md` for config options.
- `docs/CLI.md` for CLI commands.
- `docs/API.md` for public HTTP API changes.
- `docs/API_COMPATIBILITY.md` for stable API contract changes.
- `docs/ARCHITECTURE.md` for module or boundary changes.
- `docs/PROVENANCE_DESIGN.md` for source-chain semantics.
- `docs/BACKUP_AND_RECOVERY.md` for runtime data, backup, restore, or test isolation changes.

Keep internal planning notes, private workflow JSON, slides, local vaults, and generated reports out of the public branch.

## Privacy Rules

Do not commit:

- `.env`, API keys, tokens, cookies, or credentials.
- `config.yaml` with private local paths.
- `wiki/` runtime vault contents.
- Local workflow exports or credentials.
- Personal notes, Hermes sessions, PDFs, screenshots, or company documents.
- `.local-dev/` internal working notes.

If a test needs realistic-looking secrets, use fake values and assert they are redacted.

## Pull Request Checklist

- Tests pass.
- No runtime vault, raw source, secret, or private path is committed.
- New behavior is covered by tests.
- Public docs are updated when user-facing behavior changes.
- The change respects existing module boundaries.
