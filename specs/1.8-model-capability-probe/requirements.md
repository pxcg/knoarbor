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

## Requirements

- Model discovery reads provider metadata without making a generation call.
- Provider credentials and API keys are never returned by diagnostics APIs.
- Local unauthenticated providers are supported when `api_key_env` is empty.
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
- Discovery responses include model existence, detected/effective context
  window, and suggested config values.
- `POST /models/apply-capabilities` updates only allowed capability fields in
  `config.yaml`.
- `GET /doctor` can continue using the shared model gateway health check.
- Unit tests cover discovery, local unauthenticated providers, and config apply
  behavior.
