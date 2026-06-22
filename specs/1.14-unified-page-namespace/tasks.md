# 1.14 Unified Page Namespace Tasks

## P0 Contract And Current Impact Audit

- [x] Add ADR 0002 for unified page namespace and virtual facets.
- [x] Create this SDD spec.
- [x] Record code impact areas for schema, path resolution, index/search, lint,
  query/chat/UI, CLI/API/docs, and tests.
- [x] Add `PageIdentity`, `PageKind`, `PageRole`, and `PageFacet` schemas.
- [x] Add tests for page identity normalization, legacy path normalization, and
  facet deduplication.

## P1 Machine Index Virtual Facets

- [x] Extend `machine_page.v1` or introduce `machine_page.v2` with:
  - `canonical_path`;
  - `legacy_paths`;
  - `page_kind`;
  - `subject_kind`;
  - `role`;
  - `facets`;
  - `source_digest_ids`;
  - `atom_ids`;
  - migration-only `directory`.
- [x] Update Markdown page collection to scan maintained pages without relying
  only on `PAGE_TYPE_ORDER`.
- [x] Infer `page_kind`, `role`, and `facets` from frontmatter, legacy directory,
  and sections.
- [x] Keep existing query and UI behavior stable while emitting the new fields.
- [x] Add fixtures for legacy typed pages and canonical flat pages in one vault.

## P2 Resolver Compatibility

- [x] Add a canonical page resolver that accepts:
  - canonical path;
  - legacy path;
  - wikilink target;
  - title/alias match.
- [x] Add deterministic conflict reporting for slug collisions and alias
  collisions.
- [x] Update wikilink resolution to search canonical and legacy identities.
- [x] Update read-page and links APIs to return canonical path plus legacy path
  metadata when available.

## P3 Lint And Governance Migration

- [x] Replace `KNOWLEDGE_DIRS` as the primary knowledge-page classifier with
  `role=knowledge_page` and `page_kind/facets`.
- [x] Replace required-section rules keyed only by directory with rules keyed by
  page role and page kind.
- [x] Treat `sources/` as `role=source_digest` and validate source-digest
  contracts by role.
- [ ] Add lint checks for:
  - [x] missing page identity metadata;
  - [x] path alias conflicts;
  - [x] source digest stored as a knowledge page;
  - knowledge page stored in legacy typed directory after the write mode flips.
- [x] Keep old directory fields accepted as migration inputs.

## P4 Query, Chat, Graph, And UI Facets

- [x] Update query filtering so `page_dirs` becomes a legacy alias for facets.
- [x] Add explicit `facets`, `page_kind`, and `role` filters at the service
  boundary.
- [x] Update chat source/provenance classification to use page role instead of
  `path.startswith("sources/")`.
- [x] Update graph stats from `directory_counts` to `page_kind_counts` and
  `facet_counts`.
- [x] Update frontend wiki browser from hard-coded directories to virtual
  facets.
- [x] Preserve source audit browsing as a first-class view.

## P5 New Write Path

- [x] Update page planning to emit `canonical_path`, `legacy_paths`,
  `page_kind`, `subject_kind`, and `facets`.
- [x] Update draft/write contracts so new knowledge pages can write to
  `pages/<slug>.md`.
- [x] Keep source digest pages separate in `sources/`.
- [x] Make updates to existing legacy typed pages work until migration.
- [x] Add collision-safe slug allocation for the flat namespace.

## P6 Generated Views

- [x] Generate or expose `_views/Home.md`.
- [x] Generate or expose `_views/Concepts.md`.
- [x] Generate or expose `_views/Entities.md`.
- [x] Generate or expose `_views/Workflows.md`.
- [x] Generate or expose `_views/Comparisons.md`.
- [x] Generate or expose `_views/Open-Questions.md`.
- [x] Generate or expose `_views/Source-Audit.md`.
- [x] Ensure views are generated artifacts and not used as fact sources.

## P7 Controlled Physical Migration

- [x] Add dry-run migration command for selected legacy typed directories.
- [x] Move pages in controlled batches.
- [x] Rewrite wikilinks to canonical paths.
- [x] Update atom page refs and source digest affected-page refs.
- [x] Regenerate machine index and reports after migration.
- [x] Keep `legacy_paths` for migrated pages.
- [x] Add rollback instructions before enabling broad migration.

## P8 Docs And Examples

- [x] Update architecture docs after Phase 1 lands.
- [x] Update CLI/API docs after facet filters exist.
- [x] Update concepts docs after generated views exist.
- [ ] Update screenshots after frontend facet browsing lands.
- [x] Keep release notes explicit about migration status and old path support.
