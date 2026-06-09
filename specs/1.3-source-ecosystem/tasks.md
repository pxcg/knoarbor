# 1.3 Source Ecosystem Tasks

Status values:

- `[done]`: implemented and tested.
- `[next]`: next reasonable implementation work.
- `[later]`: still in 1.3 scope, but not the next change.

## Source Catalog Surface

- [done] Add `SourceCatalogService`.
- [done] Add `GET /sources`.
- [done] Add `/sources` to the public API contract.
- [done] Add `SourceCatalogResponse` and `SourceConnectorCatalogItem`.
- [done] Document the API in English and Chinese.
- [done] Add API tests for static catalog and config annotations.

## CLI Surface

- [done] Add `knoar sources --catalog`.
- [done] Preserve `knoar sources` as source preflight.
- [done] Add compact human output and JSON output.
- [done] Document CLI behavior in English and Chinese.
- [done] Add CLI tests.

## Connector Capability Contract

- [done] Add `settings_schema` to connector capability metadata.
- [done] Provide default settings schemas for existing connectors.
- [done] Ensure registered connectors expose source types and settings schema.
- [done] Add connector contract tests.
- [done] Add a connector development checklist to docs.
- [later] Decide whether connector settings schemas should include display
  metadata for the web console.

## UI Integration

- [done] Make UI diagnostics reuse `SourceCatalogService`.
- [later] Reduce remaining connector display hardcoding in the console where it
  improves maintainability without over-abstracting the UI.
- [later] Let the Sources page optionally show connector settings schema in a
  user-friendly detail panel.

## Skill Integration

- [done] Add skill `sources catalog`.
- [done] Add skill command examples and HTTP fallback docs.
- [done] Add skill helper tests.

## Documentation And Release

- [done] Add this feature spec.
- [done] Link the spec from docs index, maintainer process, development flow,
  and roadmap.
- [later] Reference the spec in the next 1.3 release notes.
