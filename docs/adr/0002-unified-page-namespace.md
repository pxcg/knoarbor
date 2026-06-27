# ADR 0002: Canonical Wiki Layout And Graph Index

## Status

Accepted

## Context

KnoArbor compiles raw materials into a maintained Markdown wiki. The durable
knowledge boundary is the page body itself: identity, summary, claims,
relations, synthesis, entities, and evidence. Physical folders must therefore
describe storage responsibility, not knowledge type.

The filesystem layout needs to stay simple for users opening the vault in
Obsidian or a normal editor, while machine indexes need enough structure for
query, chat, graph, and lint.

## Decision

Each vault uses one canonical layout:

```text
<vault>/
  raw/
  wiki/
    pages/
      <slug>.md
    sources/
      <source-digest>.md
    log.md
  maintenance/
    reports/
      ingest/
      lint/
      query/
      run-failure/
    archives/
  .knoarbor/
    index/
      manifest.json
      graph_index.json
    ledgers/
    checkpoints/
    runs/
    queue/
    locks/
    logs/
    chat/
      sessions/
```

Knowledge pages live only under `wiki/pages/`. Source digest pages live only
under `wiki/sources/`. Runtime state and machine indexes live under
`.knoarbor/`. Human-readable reports live under `maintenance/reports/`.

KnoArbor does not use physical directories for topic categories. Concept, entity,
workflow, comparison, claim, and relation semantics are represented inside the
page body and in `.knoarbor/index/graph_index.json`.

The minimum page identity frontmatter is:

```yaml
---
created: 2026-06-27 10:00:00
updated: 2026-06-27 10:00:00
content_hash: abc123
---
```

The page body carries the knowledge contract:

- `Summary`: short human-readable overview.
- `Claims`: numbered evidence-backed assertions.
- `Relations`: triples derived from claims and entities.
- `Synthesis`: readable synthesis derived from the claims.
- `Entities`: important entities mentioned by claims.
- `Evidence`: source, range, basis, and confidence for claims.

The graph index is the primary machine index. It stores page records, entity
nodes, relation edges, source references, and lookup keys needed by query,
chat, graph, and lint.

## Consequences

Positive consequences:

- Users see one clean wiki page directory plus one source audit directory.
- Obsidian users do not see reports, ledgers, checkpoints, or machine state as
  normal notes.
- Query and chat can retrieve by graph structure before reading full pages.
- Frontend views can be derived from indexes without writing generated view
  pages into the wiki.
- Page semantics can evolve without moving files between type directories.

Costs:

- Index generation must be reliable because browsing and graph views depend on
  machine indexes.
- Lint must validate page body structure rather than relying on folder names.
- Tests and fixtures must create canonical vaults; no compatibility fixture is
  part of the contract.

## Alternatives Considered

### Physical Type Directories

Rejected. Folder names such as concepts, entities, workflows, and comparisons
turn file paths into a type system and make multi-dimensional pages awkward.

### Single Flat Wiki Directory

Rejected. Source digests are audit artifacts and should not be mixed with
ordinary knowledge pages.

### Generated Physical Views

Rejected. Generated view files such as topical groups are UI/index
projections, not files written into the wiki.
