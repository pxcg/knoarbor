# API Compatibility

KnoArbor has not published a stable v1 API yet, so the pre-release line favors a small, clear public surface over compatibility with early prototype paths.

## Public API Surface

The public integration API is intentionally compact:

- `GET /health`
- `GET /runtime`
- `GET /doctor`
- `POST /ingest`
- `POST /lint`
- `POST /query`
- `POST /query/feedback`
- `GET /query/trends`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/stream`
- `POST /runs/{run_id}/cancel`
- `GET /wiki/pages`
- `GET /wiki/pages/content`
- `GET /wiki/pages/links`

Different workflow variants are selected by request fields such as `execution`, `kind`, `mode`, and `context_format`.

## Prototype Routes

Early prototype routes have been removed before the public v1 API. New workflow
variants should be represented as request fields on the compact public API
surface, not as additional top-level paths.

## Change Rules

- Public paths and required fields should not change without updating this file and the API surface tests.
- Optional response fields may be added.
- `/ui/api/*` is internal to the local management UI and is not a stable integration API.
