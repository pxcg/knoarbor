# API Compatibility

KnoArbor 1.x exposes a public local API for the CLI, web console, skills, and
external tools. The 1.x line favors a compact and clear surface while the
project continues toward the 2.0 long-term compatibility baseline.

## Public API Surface

The public integration API is intentionally compact:

- `GET /health`
- `GET /doctor`
- `POST /ingest`
- `POST /lint`
- `GET /models/providers`
- `POST /models/discover`
- `POST /models/probe`
- `POST /models/apply-capabilities`
- `POST /chat`
- `POST /chat/stream`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}`
- `PATCH /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`
- `POST /chat/sessions/{session_id}/ingest`
- `POST /chat/sessions/{session_id}/close`
- `POST /chat/sessions/{session_id}/retry`
- `POST /query`
- `POST /query/feedback`
- `GET /query/trends`
- `GET /reports`
- `GET /reports/content`
- `GET /runtime`
- `GET /sources`
- `GET /vaults`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/stream`
- `POST /runs/{run_id}/cancel`
- `GET /wiki/pages`
- `GET /wiki/pages/content`
- `GET /wiki/pages/links`

Different workflow variants are selected by request fields such as `execution`, `kind`, and `mode`.

## Prototype Routes

Early prototype routes have been removed before the public v1 API. New workflow
variants should be represented as request fields on the compact public API
surface, not as additional top-level paths.

## Change Rules

- Public paths and required fields should not change without updating this file and the API surface tests.
- Optional response fields may be added.
- `/ui/api/*` is internal to the local management UI and is not a stable integration API.
