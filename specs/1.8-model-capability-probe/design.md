# Model Capability Check Design

## Ownership

The capability belongs to the semantic/model boundary, with service orchestration
in `services/model_probe.py`.

| Layer | Responsibility |
| --- | --- |
| Semantic | Provider adapters and model discovery through provider metadata endpoints. |
| Service | Load config, choose provider, classify results, build recommendations, write explicit config updates. |
| API | Expose stable JSON endpoints without embedding provider policy. |
| UI/CLI/Skill | Call service endpoints and present results. They do not reimplement model-check logic. |

## Public API

- `GET /models/providers`
- `POST /models/discover`
- `POST /models/apply-capabilities`

The API uses provider names from `config.yaml` by default. Requests may also
carry an inline provider config for one-off checks later, but the first
implementation only requires configured providers.

## Discovery Check

OpenAI-compatible discovery uses `/models`. Ollama-compatible discovery also
uses `/api/show` through the existing adapter when context metadata is missing.
The check does not send chat completion requests or generate tokens.

Discovery returns:

- model IDs;
- whether the configured model exists;
- detected context window when the endpoint exposes it;
- configured and effective context values.

Discovery failures are reported as structured results; they do not crash the
entire diagnostics request unless the input config is invalid.

## Recommendations

Discovery responses include `suggested_config`:

- `context_window`: detected runtime context window when present;
- `max_output_tokens`: conservative output budget derived from context window.

The recommended output budget is intentionally bounded:

```text
min(8000, max(1024, floor(context_window * 0.25)))
```

This keeps local model defaults usable without silently shrinking hosted
provider configurations.

## Explicit Config Apply

`POST /models/apply-capabilities` updates only:

- `models.providers.<name>.context_window`
- `models.providers.<name>.max_output_tokens`
- `models.providers.<name>.json_mode`

It does not update API keys, base URLs, or model names.

## Rejected Alternatives

- Running a full ingest sample during every readiness check: too costly for a
  settings page and duplicates live smoke tests.
- Sending generation requests during settings checks: unnecessary for basic
  provider readiness and surprising for hosted providers.
- Silently applying detected context values during discovery: surprising config
  mutation and poor auditability.
- Branching main workflows by vendor name: model-specific behavior belongs
  behind provider adapters and model-check services.
