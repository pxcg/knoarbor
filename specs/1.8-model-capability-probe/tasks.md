# Model Capability Check Tasks

## P0

- [x] Add model capability check spec.
- [x] Add model check schemas.
- [x] Add semantic discovery helpers.
- [x] Add `ModelProbeService`.
- [x] Add public `/models/*` API endpoints.
- [x] Add tests for provider list and discovery.

## P1

- [x] Add suggested capability config values.
- [x] Add explicit config apply endpoint.
- [x] Add tests for config apply.
- [x] Document API and configuration behavior.
- [x] Isolate provider checks from global settings diagnostics refreshes.
- [x] Reuse the existing immediate-save result during provider checks instead
  of issuing a duplicate config write.
- [x] Add an explicit image-generation smoke-test endpoint and settings action.
- [x] Canonicalize API roots and exact full completion endpoints at the typed
  config boundary.
- [x] Reject ambiguous, credential-bearing, query, and fragment URLs.
- [x] Add URL-matrix tests and settings guidance for resolved endpoints.

## Later

- [ ] Add CLI commands for model discovery.
- [ ] Add workflow-level sample smoke checks.
- [ ] Add short TTL cache for repeated discovery checks.
