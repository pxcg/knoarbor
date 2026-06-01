# API Compatibility

KnoArbor has not published a stable v1 API yet, so the pre-release line favors a small, clear public surface over compatibility with early prototype paths.

## Public API Surface

The public integration API is intentionally compact:

- `GET /health`
- `GET /doctor`
- `POST /ingest`
- `POST /lint/run`
- `POST /query/search`
- `POST /query/feedback`
- `GET /query/trends`
- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/stream`
- `POST /runs/{run_id}/cancel`
- `GET /wiki/pages`
- `GET /wiki/page`
- `GET /wiki/backlinks`

Different workflow variants are selected by request fields such as `flow`, `kind`, `mode`, and `context_format`.

## Removed Prototype Routes

The following prototype routes are intentionally not part of the public API:

- `POST /ingest/run`
- `POST /ingest/document`
- `POST /ingest/file`
- `POST /runs/ingest`
- `POST /runs/ingest-file`
- `POST /runs/lint`
- `POST /runs/query`
- `GET /runs/active`
- `POST /runs/{run_id}/rerun-failed`

Use `POST /ingest` or `POST /runs` instead.

## Change Rules

- Public paths and required fields should not change without updating this file and the API surface tests.
- Optional response fields may be added.
- `/ui/api/*` is internal to the local management UI and is not a stable integration API.
