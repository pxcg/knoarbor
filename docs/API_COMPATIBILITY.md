# API Compatibility

KnoArbor 1.x exposes a public local API for the CLI, web console, skills, and
external tools. The 1.x line favors a compact and clear surface while the
project continues toward the 2.0 long-term compatibility baseline.

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
| `POST` | `/models/discover` | Discover models from a provider endpoint. |
| `POST` | `/models/probe` | Probe model availability and capabilities. |
| `POST` | `/models/apply-capabilities` | Persist detected model capabilities. |
| `POST` | `/chat` | Run one chat turn. |
| `POST` | `/chat/stream` | Run one streaming chat turn. |
| `GET` | `/chat/sessions` | List chat sessions. |
| `GET` | `/chat/sessions/{session_id}` | Read one chat session. |
| `PATCH` | `/chat/sessions/{session_id}` | Update chat session metadata. |
| `DELETE` | `/chat/sessions/{session_id}` | Delete or archive a chat session. |
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
| `GET` | `/wiki/pages` | List maintained wiki pages. |
| `GET` | `/wiki/pages/content` | Read one wiki or source digest page. |
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
- `/ui/api/*` is internal to the local management UI and is not a stable integration API.
