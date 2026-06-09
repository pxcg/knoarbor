# 1.3 Source Ecosystem Design

## Owning Layers

This spec follows the ownership rules in `docs/ARCHITECTURE.md`.

| Layer | Responsibility in this spec |
| --- | --- |
| Connector / Source | Declare connector capabilities and settings schema; discover and normalize source-specific files into `SourceDocument`. |
| Service | Expose a read-only `SourceCatalogService` for API, CLI, UI, and skill adapters. |
| Entry adapters | Provide `GET /sources`, `knoar sources --catalog`, and skill `sources catalog`. |
| Pipeline | Continue ingesting shared `SourceDocument` values; do not learn connector-specific settings. |
| Semantic | Continue reasoning over normalized source content; do not inspect connector paths or settings. |

## Public API Contract

Endpoint:

```http
GET /sources
GET /sources?config_path=/path/to/config.yaml&connector=codex
```

Response schema:

```json
{
  "schema_version": "source_catalog.v1",
  "config_path": "/path/to/config.yaml",
  "connectors": [
    {
      "schema_version": "source_connector_catalog_item.v1",
      "name": "codex",
      "version": "codex@1",
      "source_types": ["codex_chat"],
      "settings_schema": {},
      "supports_discovery": true,
      "supports_checkpoint": true,
      "supports_segmentation_hint": true,
      "requires_external_service": false,
      "configured": true,
      "enabled": true
    }
  ]
}
```

Rules:

- The endpoint is read-only.
- The endpoint does not scan local source files.
- `configured` and `enabled` are only annotated when a config file is provided.
- The endpoint belongs to the public API surface and must be listed in
  `src/knoarbor/entrypoints/api_contract.py`.

## CLI Contract

Existing command:

```bash
knoar sources
```

continues to run source preflight and normalize documents.

New read-only catalog mode:

```bash
knoar sources --catalog
knoar sources --catalog --connector codex --json
```

Rules:

- `--catalog` must not run connector discovery.
- `--json` returns the same `source_catalog.v1` schema as the API.
- Human output summarizes connector name, version, source types, and major
  capability flags.

## Skill Contract

Skill command:

```bash
python3 scripts/knoarbor.py sources catalog
python3 scripts/knoarbor.py sources catalog --connector codex
```

Rules:

- Uses public `GET /sources`.
- Does not use `/ui/api/*`.
- Safe to run for source-support or configuration questions.
- Does not start ingest or lint.

## Connector Contract

Every registered connector must expose:

- `name`
- `version`
- `source_types`
- `settings_schema`
- `supports_discovery`
- `supports_checkpoint`
- `supports_segmentation_hint`
- `requires_external_service`

Default capability inference can exist for existing connectors, but every
registered connector must pass contract tests. A connector may override
`capabilities()` to provide a custom settings schema.

## Settings Schema

The settings schema is intentionally lightweight and JSON-Schema-like. It is
not a full config DSL.

Markdown connector fields:

- `roots`
- `pattern`
- `recursive`
- `raw_output_dir`

Chat connector fields:

- `sessions_dir`
- `root`
- `session_files`
- `pattern`
- `recursive`
- `raw_output_dir`

Generic chat also supports:

- `roots`
- `patterns`

## Data Flow

```text
ConnectorRegistry
  -> connector_capabilities()
  -> SourceCatalogService
  -> GET /sources
  -> CLI/UI/Skill/external clients
```

Ingest data flow remains unchanged:

```text
Connector
  -> SourceRef
  -> RawSource
  -> SourceDocument
  -> Checkpoint / Segmentation / Semantic Ingest
```

## Rejected Alternatives

### Reuse `doctor`

Rejected because `doctor` is diagnostics-oriented and may run runtime checks.
Source catalog needs to be a cheap capability query.

### Reuse `/ui/api/config/diagnostics`

Rejected because `/ui/api/*` is not a public integration API and may change with
the console.

### Put settings explanations only in docs

Rejected because UI, CLI, skill, and external tools need a machine-readable
contract.

### Let semantic agents infer source behavior

Rejected because connector settings are deterministic integration details, not
language-understanding tasks.
