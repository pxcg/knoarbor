# ADR 0002: Unified Page Namespace And Virtual Facets

## Status

Accepted

## Context

KnoArbor's early wiki layout used physical directories such as `concepts/`,
`entities/`, `workflows/`, `comparisons/`, `queries/`, and `timelines/` to group
generated pages. This is easy to understand at small scale, but it makes the
file path act like a knowledge type boundary.

The knowledge atom ingest decision in [ADR 0001](0001-knowledge-atom-ingest.md)
defines atoms, claims, relations, and evidence as the durable knowledge
boundary. Markdown pages are readable projections. Under that model, the page
path should not be the source of truth for whether a page is a concept, entity,
workflow, comparison, or other knowledge view.

Many useful pages naturally belong to multiple types. For example, a page about
an agent framework can be an entity, an architecture case, a workflow example,
and a comparison target at the same time. A single physical directory cannot
represent that shape without forcing arbitrary choices or duplicate pages.

## Decision

KnoArbor will move toward a unified page namespace:

```text
wiki/
  pages/
    <slug>.md
  sources/
    <source-digest>.md
  _views/
    Concepts.md
    Entities.md
    Workflows.md
    Comparisons.md
    Open-Questions.md
```

Knowledge pages live under `pages/`. Page type and classification are expressed
through frontmatter, page sections, atom indexes, and virtual facets, not through
physical directory names.

Source digest pages remain separate under `sources/` because they are
provenance and audit views. They describe what a raw source contributed and are
not ordinary knowledge pages unless the user asks about the source itself.

The expected page identity model is:

```yaml
---
title: Agent Loop
canonical_path: pages/Agent-Loop.md
legacy_paths:
  - concepts/Agent-Loop.md
page_kind: concept
subject_kind: architecture_pattern
facets:
  - concept
  - workflow_pattern
  - agent_architecture
entities:
  - OpenClaw
  - Claude Code
concepts:
  - ReAct
  - Tool Calling
  - Memory
claim_ids:
  - claim_...
relation_ids:
  - rel_...
source_digest_ids:
  - source_...
---
```

Virtual facets replace physical type directories:

- `concepts` becomes `page_kind` or `facets`.
- `entities` becomes entity atoms plus page metadata.
- `workflows` becomes a page facet or relation-backed synthesis shape.
- `comparisons` becomes a page facet or relation-backed synthesis shape.
- `claims` becomes atom/index data plus a page section.
- `relations` becomes typed relation index data plus a page section.
- `sources` remains a physical provenance directory.

Generated `_views/` pages or console filters should provide human browsing
entry points for concepts, entities, workflows, comparisons, recent pages, open
questions, and source audit. These views replace the browsing role previously
played by physical type directories.

## Consequences

Positive consequences:

- A page can belong to multiple knowledge facets without duplication.
- Page movement is no longer required when type semantics evolve.
- Query and Chat can use explicit metadata and atom evidence instead of
  inferring type from a path prefix.
- Obsidian users can browse through generated views while the filesystem stays
  stable.
- The layout aligns with the atom-first model in ADR 0001.

Costs:

- Metadata, lint, and machine indexes must become stronger because directory
  names no longer provide the main type signal.
- Query, graph, reports, and the frontend need virtual-facet awareness.
- A path resolver is required during migration so legacy links and citations can
  resolve to canonical paths.
- Flat `pages/` namespaces can introduce slug collisions; collision handling
  must be explicit.

## Migration Strategy

This decision should be implemented in phases. It should not start by moving
all existing files.

1. Define the page identity contract: `canonical_path`, `legacy_paths`,
   `page_kind`, `subject_kind`, `facets`, atom ids, relation ids, and source
   digest ids.
2. Extend the machine page index with canonical path, legacy paths, page kind,
   role, facets, and source-digest role fields.
3. Update query, lint, graph, and frontend browsing to prefer virtual facets
   while old directory fields remain available as migration data.
4. Add canonical path resolution so old paths such as `concepts/X.md` can point
   to `pages/X.md` when migrated.
5. Add a new ingest write mode for canonical `pages/` output.
6. Generate `_views/` pages or equivalent console filters before broad physical
   migration, so Obsidian and filesystem browsing do not degrade.
7. Migrate existing knowledge pages in controlled batches, updating wikilinks,
   atom refs, reports, and indexes.

## Alternatives Considered

### Keep Physical Type Directories

Rejected as the long-term model because path prefixes become an implicit type
system. This makes multi-facet pages awkward and conflicts with the atom-first
model.

### Fully Flat Wiki Without Views

Rejected because a flat `pages/` directory without generated views or facet
filters would make browsing worse for Obsidian and filesystem users.

### Put Source Digests Under `pages/`

Rejected because source digests are provenance artifacts, not ordinary
knowledge pages. Keeping `sources/` separate protects the distinction between
source-level audit and maintained knowledge.

### Immediate Physical Migration

Rejected because current paths appear in wikilinks, citations, reports, run
ledgers, tests, and user bookmarks. A resolver and virtual-facet layer should
come before bulk file moves.

## Verification And Follow-Up

Follow-up work should verify:

- new pages can be indexed and retrieved by `page_kind` and `facets`;
- legacy paths resolve to canonical paths after migration;
- query and chat do not infer answer role from path prefix alone;
- graph and UI show type/facet counts instead of relying on directory counts;
- lint validates required page metadata and source digest separation;
- `_views/` or equivalent UI filters keep browsing clear after physical
  directory reduction;
- slug collision handling is deterministic and reported.
