# 1.4 Machine Index Layer Requirements

## Problem

KnoArbor retrieves from Markdown wiki pages and machine index artifacts. Earlier
drafts used a human-readable `index.md` as a routing artifact, but the durable
retrieval boundary is now `.knoarbor/index/manifest.json` plus
`.knoarbor/index/graph_index.json`.

The 1.4 line should introduce a machine index layer that improves retrieval
without requiring a vector database or heavyweight service.

## Goals

- Use `manifest.json` and `graph_index.json` as the default machine-readable
  index boundary.
- Treat `index.md` as a future optional export view, not as source of truth.
- Prefer local BM25 ranking and SQLite FTS-style durable retrieval before optional vector search.
- Give ingest, lint, query, and UI a shared index provider contract.
- Track index freshness, rebuild status, and failure states.
- Keep the default installation local and lightweight.
- Return page-level roles so query callers can distinguish primary answer
  pages, supporting context pages, and source provenance pages.

## Non-Goals

- Do not require a vector database for the default install.
- Do not replace wiki Markdown pages as the source of truth.
- Do not make query depend on a network service.
- Do not add multi-user search permissions.
- Do not let query, UI, or graph traversal depend on ad hoc retrieval payloads
  outside the index provider boundary.

## User Scenarios

### Query A Medium Vault

As a user with dozens or hundreds of pages, I can query the vault and receive
more consistent page matches than path/title-only scanning.

Acceptance criteria:

- Query can use a machine index provider.
- Query results still include source path, title, page role, excerpts, and
  trace data.
- Query results expose `role`, and responses group pages into `primary_pages`,
  `supporting_pages`, and `source_pages`.
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
- The durable provider can coexist with Markdown scanning as an implementation detail.
- Tests cover provider behavior, freshness, and fallback decisions.

## Current Status

Implemented:

- Markdown-based retrieval with field-weighted BM25 page scoring.
- Durable `.knoarbor/index/manifest.json` and `.knoarbor/index/graph_index.json`.
- Index-provider views for pages, links, sources, and search.
- Query context packs and trace metadata.
- `IndexProvider` direction documented in architecture and roadmap.
- Query trace records the active scoring model.
- Query response roles for primary answer pages, supporting context pages, and
  source provenance pages.

Still in scope for 1.4:

- Add rebuild command/API/reporting.
- Move query graph traversal to `graph_index.json`.
