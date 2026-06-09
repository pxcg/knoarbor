# 1.3 Source Ecosystem Requirements

## Problem

KnoArbor already supports Markdown notes and several local AI chat histories,
but source support has grown through connector-specific UI and workflow paths.
The 1.3 line should make sources first-class and extensible without weakening
the ingest pipeline.

Users and host-AI tools need to answer simple questions before running ingest:

- Which source connectors are supported?
- Which source types can each connector emit?
- Which connectors are configured and enabled?
- What settings does a connector accept?
- Does a connector support checkpointing and long-source segmentation?

Developers need a stable path for adding sources:

- add a connector;
- declare its capabilities and settings schema;
- test discovery, normalization, and contract metadata;
- let API, CLI, UI, and skill consume the same capability source.

## Goals

- Treat source capabilities as a public read-only contract.
- Keep source discovery separate from source capability inspection.
- Keep document preprocessing separate from source ingestion.
- Make every connector emit shared `SourceDocument` contracts.
- Make connector settings understandable without reading connector code.
- Make host-AI skills able to inspect supported sources through stable API
  capabilities rather than `/ui/api/*`.

## Non-Goals

- Do not add a database or vector index for source discovery in 1.3.
- Do not make source catalog calls scan local files.
- Do not move connector-specific parsing into semantic prompts.
- Do not require users to configure every source connector.
- Do not make ingest write to multiple vaults in one run.
- Do not bundle third-party document parser runtimes as part of this spec.

## User Scenarios

### Inspect Supported Sources

As a user, I can ask KnoArbor which source connectors are supported and see
connector names, versions, emitted source types, and required settings.

Acceptance criteria:

- `GET /sources` returns a stable `source_catalog.v1` response.
- `knoar sources --catalog` prints the same source catalog.
- The host-AI skill can call `sources catalog`.
- The operation is read-only and does not scan local files.

### Configure A Known Connector

As a user, I can inspect the expected settings for a connector such as `codex`
or `markdown` without reading Python code.

Acceptance criteria:

- Each catalog item includes a lightweight `settings_schema`.
- Markdown exposes `roots`, `pattern`, and `recursive`.
- Chat connectors expose `sessions_dir`, `root`, `session_files`, `pattern`,
  and `recursive`.

### Add A New Connector

As a developer, adding a new source should normally require connector code,
contract tests, and documentation updates, not ingest-core changes.

Acceptance criteria:

- Connector contract tests fail if a registered connector lacks source types or
  settings schema.
- Source catalog uses the connector registry as the capability source of truth.
- Ingest continues to consume only shared `SourceDocument` values after source
  normalization.

## Current 1.3 Status

Implemented:

- `GET /sources`
- `knoar sources --catalog`
- `SourceCatalogService`
- connector `settings_schema`
- skill `sources catalog`

Still in scope for 1.3:

- Reduce remaining UI hardcoding around connector display where practical.
- Add connector development guidance and a minimal connector test checklist.
- Review whether source preflight output should reference catalog metadata.
