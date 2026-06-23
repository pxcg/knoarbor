# Index Boundary

## Purpose

This note freezes the machine index boundary for KnoArbor's wiki retrieval
strategy.

The decision is:

> KnoArbor does not require `index.md` as a default wiki file. Retrieval uses a
> machine graph index made of `manifest.json` and `graph_index.json`.

`index.md` can be considered later as an optional export view for Obsidian or
AI tools without API access, but it is not part of the default architecture and
must not be treated as the source of truth.

## First-Principles Question

The first-principles question is:

> What is the smallest index that lets KnoArbor find the right wiki pages
> without duplicating the whole wiki?

The answer is:

> A graph index that locates knowledge objects, relations, and source-to-page
> contributions, plus a manifest that describes whether the graph index is
> fresh and compatible.

The index should answer "where should the system read next?", not "what does the
page fully say?" Full claims, evidence, and synthesis remain in Markdown pages.

## Default Index Layout

```text
.knoarbor/
  index/
    manifest.json
    graph_index.json
```

The wiki content surface remains:

```text
wiki/
  raw/
  sources/
  pages/
```

## `graph_index.json`

`graph_index.json` is the retrieval graph.

It stores only the minimum structure needed to locate pages and traverse the
knowledge network:

- knowledge object nodes;
- claim-backed relation edges;
- source digest to page contribution mappings.

It does not store full claims, full evidence, full synthesis, or full page text.

### Shape

```json
{
  "nodes": [
    {
      "id": "Agent Loop",
      "pages": ["pages/Agent-Loop.md"],
      "aliases": [],
      "summary": "Agent Loop is an agent runtime control loop."
    }
  ],
  "edges": [
    {
      "source": "Agent Loop",
      "predicate": "contrasts_with",
      "target": "Workflow",
      "page": "pages/Agent-Loop.md",
      "claim": "C2"
    }
  ],
  "sources": [
    {
      "source": "sources/Agent-Loop-Source.md",
      "raw": "raw/chats/session_xxx.jsonl",
      "pages": ["pages/Agent-Loop.md", "pages/Workflow.md"]
    }
  ]
}
```

### Nodes

Nodes represent knowledge objects extracted from page entities and relation
triples.

Minimum node fields:

- `id`: stable object name;
- `pages`: pages where the object appears or is maintained;
- `aliases`: optional alternative names;
- `summary`: optional short page/object preview.

Nodes are not traditional entity/concept classes. KnoArbor treats concepts,
entities, methods, protocols, systems, and named ideas as knowledge objects.

### Edges

Edges represent claim-backed relations.

Minimum edge fields:

- `source`: subject knowledge object;
- `predicate`: relation type;
- `target`: object knowledge object;
- `page`: page where the relation is maintained;
- `claim`: claim number that supports the relation.

Edges are not created from loose topical similarity. They should be extracted
from page `Relations` tables, where each relation points back to one or more
claims.

### Sources

Source mappings connect source digests to affected pages.

Minimum source fields:

- `source`: source digest path;
- `raw`: raw source path or source id;
- `pages`: knowledge pages that the source digest contributed to.

This supports source-level queries and ingest audit without making source
digests compete with knowledge pages as primary answer objects.

## `manifest.json`

`manifest.json` is the index state file. It describes `graph_index.json`; it
does not contain wiki knowledge.

It answers:

- Which index schema version is this?
- When was the graph index generated?
- Which vault does it belong to?
- Which wiki content hash does it represent?
- Is the graph index file complete and intact?
- How many pages, sources, nodes, and edges were indexed?

### Shape

```json
{
  "schema_version": "knoarbor_index.v1",
  "generated_at": "2026-06-23T12:00:00",
  "vault_id": "default",
  "wiki_hash": "abc123",
  "graph_index_hash": "def456",
  "page_count": 120,
  "source_count": 80,
  "node_count": 340,
  "edge_count": 510
}
```

### Field Meanings

- `schema_version`: graph index contract version.
- `generated_at`: index build timestamp.
- `vault_id`: vault/workspace identity.
- `wiki_hash`: hash of indexed wiki content.
- `graph_index_hash`: hash of `graph_index.json`.
- `page_count`: number of knowledge pages indexed.
- `source_count`: number of source digests indexed.
- `node_count`: number of knowledge object nodes.
- `edge_count`: number of relation edges.

## Retrieval Strategy

KnoArbor retrieval is graph-first:

```text
query
  -> identify knowledge objects
  -> find nodes in graph_index.json
  -> traverse claim-backed edges
  -> locate pages
  -> read page Claims / Evidence / Synthesis
```

Example:

```text
Question: Agent Loop 和 Workflow 的区别是什么？

1. Identify objects: Agent Loop, Workflow
2. Read graph edge: Agent Loop contrasts_with Workflow
3. Locate page: pages/Agent-Loop.md
4. Read claim: C2
5. Read evidence and synthesis from the page
```

The graph index locates what to read. Markdown pages remain the source of page
content.

## Why `index.md` Is Not Default

Original lightweight LLM-Wiki workflows often use `index.md` as a compact map
because the agent may not have a separate API, graph index, or retrieval
service. KnoArbor has an explicit machine index and query/chat services, so
`index.md` is no longer the default retrieval surface.

`index.md` is not default because:

- it duplicates machine index information;
- it can become stale;
- it can reintroduce manual or generated category pages;
- it is not needed by the graph-first retrieval strategy;
- it can confuse users by looking like a normal wiki page.

If needed later, `index.md` should be generated from `graph_index.json` and
`manifest.json` as a compact export view. It should never be hand-maintained or
treated as source of truth.

## Rejected Alternatives

- Store full claims and evidence in separate `claims.json` and `evidence.json`
  by default. This duplicates page content and turns the index into a second
  database.
- Use `index.md` as the primary retrieval entry. This is useful for minimal
  file-only agents, but not for KnoArbor's graph-first retrieval architecture.
- Maintain many specialized index files before they are needed. The first
  durable index should stay small: manifest plus graph.
- Treat shared object mention alone as a strong related-page signal. Shared
  objects can seed candidates, but claim-backed relations should dominate
  traversal.

## Frozen Principle

> The graph index locates; wiki pages explain.

`manifest.json` tells KnoArbor whether the index can be trusted.
`graph_index.json` tells KnoArbor which pages to read.
Markdown pages contain the claims, evidence, and synthesis that answer the user.
