# 1.4 Machine Index Layer Requirements

## Problem

KnoArbor currently retrieves from Markdown pages and a human-readable
`index.md`. This works for small vaults, but it couples machine retrieval to
human routing artifacts and makes freshness, rebuild state, and retrieval
quality harder to reason about.

The 1.4 line should introduce a machine index layer that improves retrieval
without requiring a vector database or heavyweight service.

## Goals

- Add a machine-readable index boundary separate from `index.md`.
- Preserve `index.md` as a human debugging and routing artifact.
- Prefer local BM25 ranking and SQLite FTS-style durable retrieval before optional vector search.
- Give ingest, lint, query, and UI a shared index provider contract.
- Track index freshness, rebuild status, and failure states.
- Keep the default installation local and lightweight.

## Non-Goals

- Do not require a vector database for the default install.
- Do not replace wiki Markdown pages as the source of truth.
- Do not make query depend on a network service.
- Do not add multi-user search permissions.
- Do not remove current Markdown retrieval until the machine index is proven.

## User Scenarios

### Query A Medium Vault

As a user with dozens or hundreds of pages, I can query the vault and receive
more consistent page matches than path/title-only scanning.

Acceptance criteria:

- Query can use a machine index provider.
- Query results still include source path, title, page type, excerpts, and
  trace data.
- Missing or stale indexes produce actionable diagnostics.

### Rebuild Index

As a user or automation, I can rebuild the machine index without mutating wiki
page content.

Acceptance criteria:

- Rebuild writes only index artifacts.
- Rebuild is safe to run repeatedly.
- Rebuild status is visible through CLI/API/UI diagnostics.

### Shared Retrieval Contract

As a developer, I can improve retrieval without changing ingest, lint, query,
and UI independently.

Acceptance criteria:

- Retrieval callers depend on an index provider interface.
- The first durable provider can coexist with the current Markdown provider.
- Tests cover provider behavior, freshness, and fallback decisions.

## Current Status

Implemented:

- Markdown-based retrieval with field-weighted BM25 page scoring.
- Human-readable `index.md`.
- Query context packs and trace metadata.
- `IndexProvider` direction documented in architecture and roadmap.
- Query trace records the active scoring model.

Still in scope for 1.4:

- Formalize provider freshness model.
- Add durable local machine index storage.
- Add rebuild command/API/reporting.
- Update query to use the provider boundary by default when available.
