# 1.14 Unified Page Namespace Requirements

## Problem

KnoArbor currently uses a `pages/` content root, but knowledge page type is still
encoded in second-level physical directories such as `pages/concepts/`,
`pages/entities/`, `pages/workflows/`, `pages/comparisons/`, `pages/queries/`,
and `pages/timelines/`.

This conflicts with the accepted atom-first design:

- [ADR 0001](../../docs/adr/0001-knowledge-atom-ingest.md) defines atoms,
  claims, relations, and evidence as the durable knowledge boundary.
- [ADR 0002](../../docs/adr/0002-unified-page-namespace.md) defines physical
  page directories as migration details, not canonical knowledge type
  boundaries.

A page can project multiple facets at once. For example, an agent framework page
can be an entity, an architecture case, a workflow example, and a comparison
target. Physical type directories force an arbitrary single identity and leak
that identity into ingest, lint, query, chat, graph, frontend, reports, CLI,
tests, and docs.

## Goals

- Introduce a durable page identity contract with canonical path, legacy paths,
  page kind, subject kind, role, and facets.
- Keep source digest pages separate from maintained knowledge pages.
- Let new knowledge pages move toward `pages/<slug>.md` while old typed paths
  remain resolvable during migration.
- Replace directory-based filtering and routing with virtual facets and page
  metadata.
- Preserve Obsidian usability through generated `_views/` pages or equivalent
  console filters.
- Keep query/chat page-first behavior while using `page_kind`, `facets`, atoms,
  and source digest role instead of path prefix assumptions.
- Make migration observable through lint, reports, and tests.

## Non-Goals

- Do not immediately move all existing user vault files.
- Do not remove legacy path resolution before a stable migration path exists.
- Do not merge source digest pages into ordinary knowledge pages.
- Do not remove human browsing categories; replace physical categories with
  virtual views and filters.
- Do not turn the file layout change into a database requirement.

## User Scenarios

### New Page Uses Unified Namespace

When a new concept-like page is created, KnoArbor can write it as
`pages/Agent-Loop.md` with `page_kind: concept` and `facets:
[concept, workflow_pattern, agent_architecture]`.

### Legacy Path Still Resolves

When a user, report, citation, or Obsidian link references
`concepts/Agent-Loop.md`, KnoArbor can resolve it to the canonical page after a
migration records `legacy_paths`.

### User Browses By Type Without Physical Type Directories

When a user opens the console or Obsidian, they can still browse Concepts,
Entities, Workflows, Comparisons, Recent Pages, Open Questions, and Source Audit
through virtual facets and generated `_views/` pages.

### Query Uses Facets Instead Of Directory Prefixes

When a query asks for workflows or concepts, retrieval filters by `page_kind` and
`facets`, not by whether the path starts with `workflows/` or `concepts/`.

### Source Digest Remains Provenance

When a source digest is created, it remains under `sources/` or is marked with a
source-digest role. Chat and query treat it as provenance unless the user asks
about sources.

## Acceptance Criteria

- A page identity model exists with `canonical_path`, `legacy_paths`,
  `page_kind`, `subject_kind`, `role`, and `facets`.
- Machine page indexes include canonical path, legacy paths, page kind, role,
  facets, source digest ids, atom ids, and a migration-only directory field.
- Path resolution can resolve canonical paths and legacy paths.
- Query, chat, graph, lint, and frontend code can consume virtual facets without
  relying on physical type directories as the primary type signal.
- Source digest pages remain distinguishable by role or page kind, not only by
  `sources/` path prefix.
- New write logic can target unified knowledge page paths without breaking old
  typed-path reads.
- Verification includes at least one fixture with both a legacy path and a
  canonical `pages/<slug>.md` path.
