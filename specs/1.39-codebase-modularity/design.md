# 1.39 Codebase Modularity Design

## Lifecycle

Implemented

## Decision

KnoArbor remains a local modular monolith. Governance changes source
organization and build-time verification, not deployment topology or product
contracts.

## Backend Dependency Direction

```text
entrypoints / CLI
  -> services
  -> pipelines
  -> semantic contracts / runtime / storage / core
```

Runtime and storage may share core schemas but do not import services,
entrypoints, or presentation adapters. Optional owner behavior is injected
through protocols or callables. Imports deferred only to avoid a known cycle are
treated as debt and removed when the owning protocol is introduced.

## Backend Module Strategy

Large modules are split only at existing responsibility boundaries:

- CLI command handlers remain aggregated while their commands share bootstrap,
  config resolution, run following, and the current test substitution surface;
  line count alone does not justify compatibility forwarding or reverse imports.
- model transport, provider adapters, structured-output handling, and metrics
  become separate semantic modules.
- transactional ingest schema/migration, task lifecycle, revision publication,
  and materialization state receive explicit internal owners before physical
  extraction.
- transactional ingest migration depends only on leaf storage integrity
  readers. Revision manifest verification and immutable machine-index snapshot
  verification do not import the lifecycle store; deferred imports may not be
  used to conceal a runtime/storage cycle.
- ingest orchestration delegates compilation, publication, and metrics to
  existing dedicated modules rather than accumulating new helpers.
- chat modules depend on capability protocols for memory, sessions, tools,
  execution, and ingest workflow rather than the application service container;
  conversation-message merge semantics have one chat-domain owner.

The architecture gate verifies dependency direction rather than file length.
Module size can prompt a responsibility review, but extraction requires a real
owner, contract, dependency, lifecycle, or independently testable behavior.

## Frontend Domain Structure

```text
renderer/src/api/
  http.ts
  scope.ts
  contracts/<domain>.ts
  <domain>.ts
  client.ts       # narrow public composition surface
  types.ts        # narrow re-export surface

renderer/src/i18n/locales/
  <language>-<domain>.ts
  data.ts         # merge and lookup only

renderer/src/components/
  shared interaction primitives
```

Domain clients own endpoint payload construction. `http.ts` alone owns
fetch, JSON parsing, error normalization, and base URL behavior. Pages consume
domain functions and never construct backend URLs.

`client.ts` is a compatibility composition surface and does not implement
domain behavior. Page and feature modules receive explicit capability slices;
the complete application context is visible only to the controller and route
composition roots. Electron preload types are the single desktop IPC contract,
consumed by the renderer through type-only imports.

Locale resources remain plain TypeScript objects. Splitting is mechanical by
stable key prefix; merge-time duplicate detection and the existing parity check
remain authoritative.

## UI Primitive Policy

Primitives are introduced only for interaction patterns already repeated at
least twice. They own accessibility and state-independent presentation, not
workflow policy. No external component framework is added in this initiative.

## Verification

- Python and renderer dependency-direction checks.
- Import-time backend cycle detection, excluding imports guarded by
  `TYPE_CHECKING`.
- TypeScript build and locale parity.
- Focused API transport/domain tests where behavior changes.
- Playwright smoke for navigation and critical dialogs.
- Full Python tests, package build, documentation governance, and diff checks.

`scripts/plan-affected-validation.py` selects only mechanically determinable
minimum gates and reports the remaining owner/direct-consumer test review. Its
risk result is a floor; durable, public, semantic, lifecycle, and release
dependencies can only raise it. R3 does not imply the full development gate.

## Rejected Alternatives

- **Tauri migration**: adds Rust while retaining the Python sidecar and does not
  address source coupling.
- **Microservices**: contradict local-first deployment and multiply lifecycle
  state.
- **Large UI framework**: introduces visual and bundle migration without fixing
  domain boundaries.
- **Mechanical maximum-line rewrite**: lowers line counts while increasing
  indirection and is not an architecture improvement.
