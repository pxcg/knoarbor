# Model Capability Probe Design

## Ownership

The capability belongs to the semantic/model boundary, with service orchestration
in `services/model_probe.py`.

| Layer | Responsibility |
| --- | --- |
| Semantic | Provider adapters, model discovery, minimal generation, structured-output generation. |
| Service | Load config, choose provider, classify results, build recommendations, write explicit config updates. |
| API | Expose stable JSON endpoints without embedding provider policy. |
| UI/CLI/Skill | Call service endpoints and present results. They do not reimplement probe logic. |

## Public API

- `GET /models/providers`
- `POST /models/discover`
- `POST /models/probe`
- `POST /models/apply-capabilities`

The API uses provider names from `config.yaml` by default. Requests may also
carry an inline provider config for one-off checks later, but the first
implementation only requires configured providers.

## Probe Levels

- `minimal`: sends a small prompt and expects exact `OK`. This verifies
  endpoint, auth, model availability, and basic chat completion behavior.
- `structured`: sends a small JSON-only prompt and validates
  `{"ok": true, "value": 1}`. This verifies structured-output suitability for
  KnoArbor semantic contracts.

Deep workflow probes are reserved for a later feature because they cost more
tokens and overlap with ingest/lint live smoke tests.

## Discovery

OpenAI-compatible discovery uses `/models`. Ollama-compatible discovery also
uses `/api/show` through the existing adapter when context metadata is missing.

Discovery returns:

- model IDs;
- whether the configured model exists;
- detected context window when the endpoint exposes it;
- configured and effective context values.

Discovery failures are reported as structured results; they do not crash the
entire diagnostics request unless the input config is invalid.

## Recommendations

Probe responses include `suggested_config`:

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
- Silently applying detected context values during discovery: surprising config
  mutation and poor auditability.
- Branching main workflows by vendor name: model-specific behavior belongs
  behind provider adapters and probe services.
