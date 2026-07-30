# Model Capability Check Requirements

## Goal

KnoArbor needs a stable model diagnostics capability that tells users whether a
configured model provider can support semantic ingest and lint workflows. The
capability must work for hosted OpenAI-compatible providers and local
OpenAI-compatible runtimes such as vLLM and Ollama.

## User Scenarios

- A user adds a DeepSeek, OpenAI, vLLM, Ollama, or custom OpenAI-compatible
  provider and wants to know whether KnoArbor can reach it.
- A user wants to fetch available model IDs from a provider endpoint instead of
  manually typing model names.
- A user wants KnoArbor to detect or recommend `context_window` and
  `max_output_tokens`.
- A user wants to apply detected capability values to `config.yaml` through an
  explicit action.
- A user configures an image provider and wants to verify its real generation
  contract without confusing that action with text-model metadata discovery.

## Requirements

- OpenAI-compatible provider `base_url` represents the API root. It may contain
  a vendor path such as `/compatible-mode/v1`; `/v1` is not mandatory.
- The settings boundary accepts either the API root or an exact full
  `/chat/completions` endpoint, removes only that exact endpoint suffix, and
  persists one canonical API root without a trailing slash.
- Provider URLs must be absolute HTTP(S) URLs without credentials, query
  parameters, or fragments. Partial or misspelled endpoint suffixes are
  rejected instead of guessed.
- Model discovery and generation derive `/models` and `/chat/completions` from
  the same canonical API root.
- Image-provider settings keep endpoint path separate from the canonical base
  URL and apply the same exact-suffix normalization for the supported image and
  chat-image endpoints.
- Model discovery reads provider metadata without making a generation call.
- Text-model checks wait for any current provider-form save and then call only
  model discovery. They do not repeat an already persisted save or wait for
  global diagnostics, source scans, or unrelated provider refreshes.
- Image providers use a separate, explicit smoke test because image endpoints
  do not expose one common metadata contract. The smoke test performs one real
  generation and may therefore take provider generation time and incur usage.
- Provider credentials and API keys are never returned by diagnostics APIs.
- Local unauthenticated providers are supported when `api_key` is empty.
- Capability results are structured and can be consumed by API, CLI, UI, and
  host-AI skills.
- Configuration writes are explicit. Discovery calls may recommend config changes,
  but they do not mutate `config.yaml`.
- Error states are classified into user-readable categories: unreachable
  endpoint, authentication failure, unsupported endpoint, model not found,
  timeout, and invalid provider response.

## Non-Goals

- Multi-provider routing and automatic fallback are outside this feature.
- Downloading local models is outside this feature.
- Provider-specific non-OpenAI protocols are outside the first implementation.
- Benchmarking model quality or ranking providers is outside this feature.

## Acceptance Criteria

- `GET /models/providers` returns configured providers without secrets.
- `POST /models/discover` returns model IDs and detected context metadata when
  the endpoint supports discovery.
- `POST /models/image-probe` performs one explicit image-generation smoke test
  and returns bounded status metadata without returning generated image bytes.
- Discovery responses include model existence, detected/effective context
  window, and suggested config values.
- `POST /models/apply-capabilities` updates only allowed capability fields in
  `config.yaml`.
- `GET /doctor` can continue using the shared model gateway health check.
- Unit tests cover discovery, local unauthenticated providers, and config apply
  behavior.
- Contract tests cover root URLs, trailing slashes, exact full endpoints,
  vendor-prefixed roots, and rejected ambiguous URLs.
