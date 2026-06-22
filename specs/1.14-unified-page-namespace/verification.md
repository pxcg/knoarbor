# 1.14 Unified Page Namespace Verification

## Automated Checks

Phase-specific checks should be added as implementation lands. The initial
contract check should use:

```bash
uv run python -m unittest discover tests
uv run ruff check .
```

Targeted tests to add:

```bash
uv run python -m unittest \
  tests.test_page_identity \
  tests.test_wiki_paths \
  tests.test_wiki_index \
  tests.test_query_pipeline \
  tests.test_lint_pipeline
```

## Required Fixtures

Add fixtures that cover:

- a legacy typed knowledge page such as `concepts/Agent-Loop.md`;
- a canonical unified page such as `pages/Agent-Loop.md`;
- a source digest page under `sources/Agent-Loop-Source.md`;
- a page with `legacy_paths`;
- a page with multiple facets;
- a slug collision case;
- wikilinks that target old and new paths.

## Behavioral Gates

### Page Identity

- Canonical path is stable and normalized.
- Legacy paths are normalized and deduplicated.
- Page kind and facets can represent a multi-facet page.
- Source digest role is distinguishable from ordinary knowledge pages.

### Index

- Machine index includes canonical path, legacy paths, page kind, role, facets,
  source digest ids, and atom ids.
- Existing pages in typed directories remain indexed during migration.
- New flat pages can be indexed.
- Directory remains only as a migration/debug field.

### Resolver

- `concepts/Agent-Loop.md` can resolve to a migrated canonical page when
  `legacy_paths` includes it.
- `pages/Agent-Loop.md` resolves directly.
- `[[Agent Loop]]`, `[[concepts/Agent-Loop]]`, and
  `[[pages/Agent-Loop]]` resolve deterministically when unambiguous.
- Ambiguous aliases produce a lint/report issue instead of arbitrary resolution.

### Lint

- Knowledge-page checks use role/kind/facets, not only directory.
- Source digest checks use source digest role, not only `sources/` path prefix.
- Workflow/timeline/comparison checks still run for facet-matched pages.
- Missing identity metadata is reported before physical migration.

### Query And Chat

- Query can filter by facets/page kind when implemented.
- Existing `page_dirs` behavior continues during transition as a legacy alias.
- Chat citations and evidence roles do not depend only on `path.startswith`.
- Source digest pages are used for provenance unless the user asks about
  sources.

### Frontend And Graph

- Wiki browser can show virtual facets.
- Graph can display page-kind and facet counts.
- Source audit remains discoverable.
- Flat pages and legacy typed pages can both be opened.

### Migration

- Dry-run reports all planned moves, conflicts, rewritten links, and skipped
  paths.
- Real migration updates wikilinks, atom refs, source digest affected pages, and
  machine indexes.
- Rollback guidance exists before broad migration is enabled.

Current migration command:

```bash
uv run knoar vaults migrate-namespace --vault <vault-path>
```

This command is a dry-run by default. It reports planned moves from legacy typed
knowledge directories into the flat namespace and does not write files. Apply is
explicit:

```bash
uv run knoar vaults migrate-namespace --vault <vault-path> --apply
```

Apply is blocked when flat namespace conflicts exist. Source digest pages remain
under `sources/`, generated `_views/` pages are regenerated, and apply writes a
maintenance report with rollback notes.

## Known Risks

- Flat namespaces create slug collisions that old typed directories avoided.
- Old reports and run ledgers may reference legacy paths for a long time.
- Obsidian users may lose browsing clarity if `_views/` or frontend facets are
  not implemented before physical migration.
- Query quality can regress if directory priors are removed before page metadata
  and facet indexes are populated.
- Source digest pages can be misused as answer pages if role classification is
  incomplete.
