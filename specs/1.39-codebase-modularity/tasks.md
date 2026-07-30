# 1.39 Codebase Modularity Tasks

## Lifecycle

Implemented

## Architecture Gates

- [x] Add backend and renderer dependency-direction governance.
- [x] Add the governance commands to local development gates.
- [x] Remove line-count enforcement and document responsibility-based review.

## Backend

- [x] Remove reverse service imports from pipeline/runtime module initialization.
- [x] Review CLI handler ownership and retain the cohesive aggregate until a
  compatibility-free domain boundary exists.
- [x] Prevent new responsibility growth in ingest, semantic gateway, and
  transactional runtime owners.
- [x] Add executable import-boundary checks.

## Frontend

- [x] Extract shared API scope handling and domain clients.
- [x] Split TypeScript contracts by domain behind stable re-exports.
- [x] Split locale resources by language/domain with duplicate and parity checks.
- [x] Introduce a shared primitive for repeated dialog behavior.
- [x] Preserve critical projection-edit and lint-result interaction coverage.

## Closure

- [x] Update architecture, development, and verification documentation.
- [x] Run focused and full verification.
- [x] Repeat responsibility and dependency review and remove obsolete exceptions.

## Post-Closure Governance Correction

- [x] Extract leaf revision and machine-index integrity readers from aggregate
  storage writers.
- [x] Remove the transactional-ingest migration's deferred storage imports.
- [x] Make the architecture gate reject import-time backend module cycles.
- [x] Verify transactional migration, revision publication, materialization,
  retrieval snapshot reads, and architecture-cycle detection with focused tests.
- [x] Make Electron preload the single desktop IPC type-contract owner.
- [x] Reduce the renderer API client to a domain composition surface and retain
  one shared JSON/SSE error boundary.
- [x] Replace page access to the full application context with explicit
  capability slices.
- [x] Replace Chat's application-container dependency with narrow capability
  protocols and consolidate conversation-message merge semantics.
- [x] Make the application service composition root construct the shared ingest
  coordinator exactly once; API adapters consume the pre-wired container.
- [x] Remove the obsolete QueryPipeline index-provider compatibility parameter.
- [x] Add executable affected-validation planning without default full tests,
  desktop packaging, or `dev-check.sh` escalation.
