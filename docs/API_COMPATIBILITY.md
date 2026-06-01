# API Compatibility Policy

KnoArbor exposes local HTTP APIs for the bundled console, CLI helpers, workflow
tools, and AI-tool skills. This document defines what is stable during the v0.x
line and how breaking changes should be handled.

## Public Stable Surface

The public v0.x API surface is documented in [API Reference](API.md) and tracked
in `src/knoarbor/entrypoints/api_contract.py`.

Stable endpoint families:

- `GET /health`
- `GET /doctor`
- `POST /ingest/run`
- `POST /ingest/document`
- `POST /ingest/file`
- `POST /lint/run`
- `POST /query/search`
- `POST /query/feedback`
- `GET /query/trends`
- `POST /runs/ingest`
- `POST /runs/ingest-file`
- `POST /runs/lint`
- `POST /runs/query`
- `GET /runs`
- `GET /runs/active`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/stream`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/rerun-failed`
- `GET /wiki/pages`
- `GET /wiki/page`
- `GET /wiki/backlinks`

## Internal UI Surface

`/ui/api/*` is internal to the bundled web console. It may change as the UI
evolves. External tools should use the public endpoints above.

`GET /` is the primary console entry. `GET /ui` is a compatibility alias.

## Compatibility Rules

During the v0.x alpha line:

- Endpoint paths and HTTP methods should remain stable.
- Required request fields should not be removed or silently repurposed.
- Core response field meanings should remain stable.
- New optional request fields are allowed.
- New response fields are allowed.
- Error responses must use the shared error envelope and stable error codes.
- Deprecated public endpoints should remain available for at least one minor
  release unless they are unsafe.

Breaking changes require:

1. Changelog entry.
2. Release note migration section.
3. API documentation update.
4. Contract test update.
5. Clear replacement path when possible.

## Schema Versioning

Responses with durable structure should include a `schema_version` field when
the payload may be consumed by external tools.

Examples:

- `wiki_query.v1`
- `query_trace.v1`
- `run_record.v1`
- `source_document.v1`

Additive fields do not require a new schema version. Removing fields or changing
field meaning does.

## Testing Expectations

API compatibility should be guarded by:

- contract lists in `api_contract.py`;
- unit tests for stable endpoint presence;
- OpenAPI inspection for public routes;
- release checklist review for API/CLI compatibility.

Before a release, verify:

```bash
uv run python -m unittest discover tests
scripts/release-readiness.py
```
