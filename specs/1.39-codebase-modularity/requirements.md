# 1.39 Codebase Modularity Requirements

## Lifecycle

Implemented

## Ownership

This specification owns internal module boundaries, dependency direction,
frontend domain organization, static-analysis policy, and code-size governance.
Feature behavior remains owned by the existing feature specifications.

## Problem

KnoArbor's core stack remains suitable for a local-first desktop knowledge
application, but several backend and frontend modules aggregate unrelated
responsibilities. Manual API types, monolithic locale data, and weak dependency
enforcement make feature changes increasingly expensive and allow circular
imports or cross-layer policy leaks.

## Goals

1. Preserve Python/FastAPI/SQLite and React/TypeScript/Vite/Electron.
2. Give backend modules one stable responsibility and enforce inward dependency
   direction.
3. Organize frontend API contracts, clients, and locale data by product domain.
4. Establish shared UI primitives only where repeated interaction behavior
   already exists.
5. Add executable governance for module growth, dependency cycles, API contract
   parity, and critical UI behavior.
6. Preserve all public API, CLI, vault, storage, and workflow behavior.

## Non-Goals

- Microservices, Redis, Celery, an ORM, or an external workflow engine.
- A React, Electron, or CSS rewrite.
- Redux, a large component framework, or a micro-frontend architecture.
- Mechanical splitting that creates pass-through modules without ownership.
- Migrating unittest to another test framework.

## Requirements

- R1: Entry adapters depend on services; services coordinate pipelines;
  pipelines depend on core/runtime/storage contracts. Lower layers do not import
  entrypoints or UI adapters.
- R2: Cross-layer calls use typed contracts or protocols rather than import-time
  reverse dependencies.
- R3: Modules are split when they contain independently owned behavior,
  introduce unrelated dependencies, or require separate lifecycle/testing.
  File length is diagnostic information and never an automatic split rule.
- R4: Frontend API clients and contracts are grouped by domain while retaining
  one shared transport and error boundary.
- R5: Locale resources are grouped by language and domain, merged once, and
  retain automated English/Chinese key parity.
- R6: Shared UI primitives own repeated dialog, command, form, loading, and
  error interaction behavior; pages retain domain composition.
- R7: The renderer continues to lazy-load graph, Mermaid, and other heavy
  feature chunks.
- R8: All existing public behavior and persisted data remain compatible.

## Acceptance Criteria

- Architecture dependency-direction checks run in `dev-check.sh`.
- No backend dependency cycle is introduced in the governed package graph.
- Frontend build and Playwright smoke pass after domain extraction.
- Python tests and package builds pass without compatibility branches.
- Targeted aggregation modules have coherent responsibility boundaries.

