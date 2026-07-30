# API Compatibility

KnoArbor exposes a public local API for the CLI, desktop app, host-AI skills,
and external tools. The API favors a compact and clear surface while the
desktop-first product line continues to evolve.

## Public API Surface

The public integration API is method-aware. Method, path, request schema,
response schema, and error envelope form one contract.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check. |
| `GET` | `/doctor` | Runtime readiness diagnostics. |
| `POST` | `/ingest` | Start or run knowledge compilation. |
| `POST` | `/lint` | Start or run wiki maintenance. |
| `GET` | `/models/providers` | List configured model providers. |
| `GET` | `/models/image-providers` | List configured image-generation providers. |
| `POST` | `/models/image-probe` | Run an explicit image-generation smoke test. |
| `POST` | `/models/discover` | Discover models from a provider endpoint. |
| `POST` | `/models/apply-capabilities` | Persist selected model limits. |
| `POST` | `/chat` | Run one chat turn. |
| `POST` | `/chat/stream` | Run one streaming chat turn. |
| `GET` | `/chat/sessions` | List paginated chat-session summaries (`limit`, `offset`, `total_count`, `has_more`). |
| `GET` | `/chat/sessions/{session_id}` | Read one chat session. |
| `PATCH` | `/chat/sessions/{session_id}` | Update chat session metadata. |
| `DELETE` | `/chat/sessions/{session_id}` | Delete or archive a chat session. |
| `DELETE` | `/chat/sessions/{session_id}/turns/{turn_id}` | Delete one turn with session revision protection. |
| `POST` | `/chat/sessions/{session_id}/ingest` | Compile one chat session through ingest. |
| `POST` | `/chat/sessions/{session_id}/close` | Close one chat session. |
| `POST` | `/chat/sessions/{session_id}/retry` | Retry the latest failed chat answer. |
| `POST` | `/query` | Query wiki evidence without answer-model generation. |
| `POST` | `/query/feedback` | Record query feedback. |
| `GET` | `/query/trends` | Read query trend summaries. |
| `GET` | `/reports` | List reports. |
| `GET` | `/reports/content` | Read report content. |
| `GET` | `/runtime` | Read runtime integration context. |
| `GET` | `/sources` | Read source connector catalog. |
| `GET` | `/vaults` | List configured vault profiles. |
| `GET` | `/runs` | List workflow runs. |
| `GET` | `/runs/{run_id}` | Read one workflow run. |
| `GET` | `/runs/{run_id}/events` | Read run events. |
| `GET` | `/runs/{run_id}/stream` | Stream run events. |
| `POST` | `/runs/{run_id}/cancel` | Request cancellation. |
| `POST` | `/ingest/materialization/rebuild` | Rebuild deterministic projections and indexes from committed facts. |
| `GET` | `/wiki/pages` | List maintained wiki pages. |
| `GET` | `/wiki/pages/content` | Read one wiki or source record page. |
| `PATCH` | `/wiki/pages/content` | Edit allowed structured projection fields. |
| `DELETE` | `/wiki/pages/content` | Delete one maintained page through its owning service. |
| `PATCH` | `/wiki/pages/raw` | Submit a revised Raw source through standard queued ingest. |
| `GET` | `/wiki/pages/relations` | Read page links and relation context. |

Different workflow variants are selected by request fields such as `execution`, `kind`, and `mode`.

## Prototype Routes

Early prototype routes have been removed before the public v1 API. New workflow
variants should be represented as request fields on the compact public API
surface, not as additional top-level paths.

## Change Rules

- Public methods, paths, request fields, and required response fields are
  updated together with this file and the API surface tests.
- Optional response fields may be added.
- Desktop-local renderer endpoints are internal to the packaged desktop app and are not stable integration APIs.
