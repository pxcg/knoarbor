# Contributing

Thanks for considering a contribution to KnoArbor.

KnoArbor is a local-first knowledge pipeline. Contributions should preserve three boundaries:

- Connectors read sources and produce shared source contracts.
- Pipelines orchestrate ingest, lint, query, write, and maintenance.
- Semantic steps use explicit prompt contracts and validated JSON schemas.

Avoid adding hidden fallback behavior. If a reliability mechanism is needed, make it explicit in configuration, tests, reports, and documentation.

## Branch Model

- `main`: public release branch.
- `dev`: local development branch.

Open pull requests against `dev` unless maintainers request otherwise. Release changes are promoted from `dev` to `main`.

## Development Setup

```bash
uv sync
cp config.example.yaml config.yaml
cp .env.example .env
```

For semantic workflows, set at least one model provider key in `.env`.

## Tests

Run before opening a pull request:

```bash
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

## Documentation

Update documentation when behavior changes:

- `README.md` for user-facing setup or project positioning.
- `docs/CONFIGURATION.md` for config options.
- `docs/CLI.md` for CLI commands.
- `docs/API.md` for public HTTP API changes.
- `docs/ARCHITECTURE.md` for module or boundary changes.
- `docs/PROVENANCE_DESIGN.md` for source-chain semantics.

Keep internal planning notes, private workflow JSON, slides, local vaults, and generated reports out of the public branch.

## Privacy Rules

Do not commit:

- `.env`, API keys, tokens, cookies, or credentials.
- `config.yaml` with private local paths.
- `wiki/` runtime vault contents.
- `n8n/` workflows or credentials.
- Personal notes, Hermes sessions, PDFs, screenshots, or company documents.
- `.local-dev/` internal working notes.

If a test needs realistic-looking secrets, use fake values and assert they are redacted.

## Pull Request Checklist

- Tests pass.
- No runtime vault, raw source, secret, or private path is committed.
- New behavior is covered by tests.
- Public docs are updated when user-facing behavior changes.
- The change respects existing module boundaries.
