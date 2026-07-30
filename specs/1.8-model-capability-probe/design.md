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
- `POST /models/image-probe`

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

The settings UI persists edited provider fields through its existing immediate
save behavior. A provider check waits for the latest in-flight settings save,
then reads that persisted configuration; it does not issue a second,
check-specific save. The check remains isolated from global configuration
diagnostics, source catalog refreshes, and MinerU readiness checks.

## Provider URL Boundary

`core.config` owns deterministic provider URL normalization so form writes,
YAML loads, model discovery, and generation consume the same value. For an
OpenAI-compatible provider it:

1. parses one absolute HTTP(S) URL;
2. rejects embedded credentials, query parameters, and fragments;
3. removes trailing slashes;
4. removes one exact `/chat/completions` suffix when present;
5. rejects partial completion suffixes instead of guessing.

The canonical value remains `base_url`. The adapters append `/models` or
`/chat/completions`. They never independently repair or reinterpret the path.
Image provider normalization also separates an exact supported endpoint suffix
from `base_url` into `endpoint_path`.

## Image Provider Smoke Test

Image-generation providers use either an images endpoint or a chat-completions
image contract. There is no shared metadata operation that proves both
contracts, so `POST /models/image-probe` performs one explicit real generation.
It returns availability, elapsed time, image count, MIME types, and a bounded
error classification. It never returns generated URLs, base64 content, API
keys, or raw provider payloads.

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
  text-provider readiness and surprising for hosted text providers. Image
  generation is the exception and is exposed as a separately labelled,
  explicit smoke test.
- Refreshing global diagnostics and source catalogs after a provider check:
  unrelated work makes a sub-second metadata request appear slow and blurs
  error ownership.
- Silently applying detected context values during discovery: surprising config
  mutation and poor auditability.
- Branching main workflows by vendor name: model-specific behavior belongs
  behind provider adapters and model-check services.
