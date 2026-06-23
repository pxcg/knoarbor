# 1.14 Unified Page Namespace Design

## Design Summary

The migration separates physical storage from knowledge classification.

Current layout:

```text
vault/pages/concepts/Agent-Loop.md
vault/pages/entities/OpenClaw.md
vault/pages/workflows/Agent-Loop-Execution.md
vault/pages/sources/Agent-Loop-Source.md
```

Target layout:

```text
vault/wiki/pages/Agent-Loop.md       # or current content root pages/Agent-Loop.md
vault/wiki/pages/OpenClaw.md
vault/wiki/sources/Agent-Loop-Source.md
vault/wiki/_views/Concepts.md
```

The exact outer `wiki/` root depends on the active vault layout. The invariant is
that knowledge page identity is no longer encoded by a second-level type
directory. Classification lives in metadata, atom indexes, and virtual facets.

## Page Identity Contract

Add a stable internal page identity shape:

```text
PageIdentity
- canonical_path: pages/Agent-Loop.md
- legacy_paths: [concepts/Agent-Loop.md, pages/concepts/Agent-Loop.md]
- title: Agent Loop
- page_kind: concept | entity | workflow | comparison | timeline | query | note | source_digest
- subject_kind: architecture_pattern | product | organization | method | quote | ...
- role: knowledge_page | source_digest | generated_view | report
- facets: [concept, workflow_pattern, agent_architecture]
- atom_ids: [...]
- relation_ids: [...]
- source_digest_ids: [...]
```

The model can be implemented first as a schema and helper functions. It does not
require immediate physical migration.

## Impact Review

### Schema And Page Type Constants

Current hot spots:

- `src/knoarbor/core/wiki_schema.py`
- `src/knoarbor/core/schemas/wiki_page_plan.py`
- `src/knoarbor/core/schemas/wiki_write.py`

Current risk:

- `CONTENT_PAGE_DIRS`, `PAGE_TYPE_ORDER`, `AI_WRITABLE_DIRS`, and `WikiPageDir`
  act as a type system.
- `WikiDraft.page_dir` and relation/page planning prompts require old directory
  values.

Migration target:

- Introduce `PageKind`, `PageRole`, and `PageFacet`.
- Keep legacy directory constants as migration inputs only.
- Replace `page_dir` as the long-term semantic field with `canonical_path` plus
  `page_kind/facets`.

### Path Resolution And Writes

Current hot spots:

- `src/knoarbor/storage/wiki_paths.py`
- `src/knoarbor/storage/wiki_writer.py`
- `src/knoarbor/pipelines/write.py`
- `src/knoarbor/storage/wiki_init.py`

Current risk:

- `resolve_wiki_page()` rejects paths outside `AI_WRITABLE_DIRS`.
- `write_draft()` writes to `content_root / draft.page_dir`.
- `init_wiki_vault()` creates typed directories under `pages/`.
- `migrate_wiki_pages_layout()` only migrates legacy root directories into the
  current `pages/<type>/` layout.

Migration target:

- Add a resolver that accepts canonical paths, legacy paths, and source digest
  paths.
- Add a canonical path allocator for `pages/<slug>.md` and source digest paths.
- Keep old writer behavior until page planning emits canonical identity data.
- Add explicit collision handling for flat page slugs.

### Machine Index And Search

Current hot spots:

- `src/knoarbor/storage/wiki_index.py`
- `src/knoarbor/retrieval/markdown.py`
- `src/knoarbor/retrieval/index_provider.py`
- `src/knoarbor/retrieval/wiki_links.py`

Current risk:

- index freshness scans `PAGE_TYPE_ORDER` directories;
- page records store `directory` as a primary field;
- retrieval filters `page_dirs` by physical directory;
- wikilink resolution scans typed directories and will miss flat pages.

Migration target:

- index all maintained Markdown pages under the readable page root, excluding
  raw, reports, machine state, and generated non-content files.
- add `canonical_path`, `legacy_paths`, `page_kind`, `role`, `facets`, and
  `source_digest_role` to machine page records;
- reinterpret `page_dirs` as legacy facet filters during transition;
- resolve wikilinks by canonical path, legacy path, title, alias, and generated
  page identity.

### Lint And Governance

Current hot spots:

- `src/knoarbor/maintenance/lint_rules.py`
- `src/knoarbor/maintenance/lint_scanners.py`
- `src/knoarbor/maintenance/lint_collection.py`
- `src/knoarbor/maintenance/wiki_lint.py`

Current risk:

- `KNOWLEDGE_DIRS` determines which pages need source digest links and graph
  health.
- required sections are keyed by directory.
- timeline and workflow quality checks look at `page.directory`.

Migration target:

- classify pages by `role`, `page_kind`, and `facets`;
- validate required metadata for knowledge pages and source digests;
- keep specialized checks for workflow/timeline/comparison facets;
- add migration checks for missing canonical path, path alias conflicts, and
  source digest misclassification.

### Query, Chat, Graph, And UI

Current hot spots:

- `src/knoarbor/services/wiki_search.py`
- `src/knoarbor/services/chat_agent.py`
- `src/knoarbor/services/chat_evidence.py`
- `web/src/pages/WikiPage.tsx`
- `web/src/pages/GraphPage.tsx`
- `web/src/pages/ChatPage.tsx`

Current risk:

- query uses `page_dirs` as directory filters;
- chat treats source pages with `path.startswith("sources/")`;
- the wiki browser has a hard-coded directory list;
- graph displays `directory_counts`.

Migration target:

- query accepts virtual facet filters while keeping old `page_dirs` as aliases;
- chat classifies source/provenance pages by role or page kind;
- the wiki browser groups by virtual facets and generated views;
- graph displays `page_kind` and `facet` counts.

### CLI, API, Docs, Tests

Current hot spots:

- `src/knoarbor/cli_commands/parser.py`
- `docs/API.md`, `docs/CLI.md`, `docs/ARCHITECTURE.md`, `docs/CONCEPTS.md`
- fixtures and tests that assert `concepts/...`, `entities/...`, or
  `sources/...`.

Current risk:

- public examples teach physical type directories;
- tests lock the old layout too deeply;
- CLI `--dir` and API `page_dirs` names are directory-oriented.

Migration target:

- keep CLI/API behavior stable while documenting directory filters as legacy
  aliases;
- add new `--facet` / `facets` contract after service layer supports it;
- update examples only after the resolver and index support canonical paths.

## Migration Phases

### Phase 0: Contract And Audit

- Add page identity schema and tests.
- Document current directory dependencies.
- Keep runtime behavior unchanged.

### Phase 1: Virtual Facet Index

- Extend machine page records with identity/facet fields.
- Read page metadata to classify `page_kind`, `role`, and `facets`.
- Continue emitting `directory` as a migration field.
- Make lint/query/graph/UI consume facets where possible.

### Phase 2: Resolver Compatibility

- Add canonical and legacy path resolution.
- Resolve old links and citations to canonical pages when metadata provides
  aliases.
- Add slug collision detection and reports.

### Phase 3: New Write Path

- Let page planning emit canonical path and facets.
- Allow new knowledge pages to write to `pages/<slug>.md`.
- Keep source digest write path separate.
- Keep old typed-directory updates readable and updatable.

### Phase 4: Generated Views

- Generate or expose virtual views for concepts, entities, workflows,
  comparisons, recent pages, open questions, and source audit.
- Update frontend wiki browser and graph to use these facets.

### Phase 5: Controlled Physical Migration

- Add a migration command that moves selected old typed paths to canonical
  paths.
- Update wikilinks, atom page refs, machine index, and reports.
- Keep `legacy_paths` for at least one stable release cycle after migration.

## Rejected Alternatives

### Move All Files First

Rejected because existing paths appear in reports, citations, tests, wikilinks,
atom refs, and user workflows.

### Keep Directory Types Forever

Rejected because it conflicts with the atom-first model and forces one physical
type for multi-facet pages.

### Remove Browsing Categories

Rejected because users and Obsidian need visible entry points. Categories move
to virtual views and facets, not away from the product.
