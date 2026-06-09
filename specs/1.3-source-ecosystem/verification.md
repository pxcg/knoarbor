# 1.3 Source Ecosystem Verification

## Automated Checks

Run these after changes touching source catalog, connector capabilities, source
preflight, or skill source operations:

```bash
uv run python -m unittest tests.test_connector_contracts tests.test_api_surface tests.test_cli tests.test_skill_query_helper tests.test_ui_api
uv run ruff check src tests scripts integrations
uv run python scripts/check-doc-links.py
```

Before release candidates, run the full gates from `docs/TESTING.md` and
`docs/RELEASE_CHECKLIST.md`.

## Contract Tests

Required coverage:

- `ConnectorRegistry().capabilities()` includes all registered connectors.
- Every registered connector has:
  - source types;
  - settings schema;
  - checkpoint flag;
  - segmentation hint flag;
  - external service flag.
- `GET /sources` returns `source_catalog.v1`.
- `GET /sources?config_path=...` annotates `configured` and `enabled`.
- `knoar sources --catalog --json` returns the same schema.
- Skill `sources catalog` calls `/sources`, not `/ui/api/*`.

## Manual Smoke

```bash
uv run knoar sources --catalog
uv run knoar sources --catalog --connector codex --json
uv run knoar serve
```

Then inspect:

```http
GET /sources
GET /sources?connector=markdown
```

Expected behavior:

- catalog calls return quickly;
- no local source folders are scanned;
- no vault files are written;
- configured/enabled are false when no config is provided;
- configured/enabled reflect the provided config when `config_path` is passed.

## Regression Risks

- Accidentally making `/sources` perform connector discovery, causing UI or
  skill calls to become slow.
- Duplicating connector capability metadata between UI, docs, and connector
  code.
- Adding source-specific logic to ingest semantic prompts instead of connector
  normalization.
- Treating settings schema as a complete config editor DSL too early.

## Release Evidence

For a 1.3 release note, mention:

- public source catalog API;
- CLI source catalog mode;
- connector settings schema;
- skill source catalog operation;
- tests that cover connector metadata and public API behavior.
