# 1.4 Machine Index Layer Design

## Owning Layers

| Layer | Responsibility |
| --- | --- |
| Retrieval / Index | Provider interface, index records, freshness checks, search execution, rebuild status. |
| Storage | Low-level index artifact paths and atomic writes. |
| Pipeline Query | Consume provider results and build context packs. |
| Pipeline Ingest / Lint | Trigger scoped refresh only through the provider contract. |
| Entry Adapters | Expose rebuild/status commands and HTTP surfaces when stabilized. |
| UI | Display index freshness and rebuild state; do not implement indexing logic. |

## Target Boundary

```text
wikis pages
  -> PageIndexRecord
  -> MachineIndexProvider
      -> MarkdownIndexProvider
      -> SQLiteFtsIndexProvider
      -> optional VectorIndexProvider
  -> Query BM25 seed retrieval
  -> graph_index relation expansion
  -> Query / Lint / Ingest related-page lookup
```

The durable local graph boundary is:

```text
.knoarbor/
  index/
    manifest.json
    graph_index.json
```

Compatibility payloads such as `pages.json`, `links.json`, `sources.json`, and
`search.json` can remain while UI/query code is migrated. `index.md` is not a
default retrieval surface; if introduced again, it should be generated as an
optional export view from the machine index.

Query consumes the machine index in two steps:

1. `pages.json` materializes searchable pages and keeps page-level BM25 as the
   deterministic entry retrieval layer.
2. `graph_index.json` expands those seed pages through shared entities,
   explicit relation triples, and source-audit links. This preserves wiki-style
   page recall without turning the system back into chunk-level RAG.

## Public Contract Candidates

The exact public surface is not frozen yet. Candidate surfaces:

```bash
knoar index status
knoar index rebuild
```

```http
GET /index/status
POST /index/rebuild
```

These should only become public after the provider contract and report schema
are tested. Until then, keep index work behind internal services.

## Freshness Model

Index freshness should compare:

- page path;
- page content hash or modified timestamp;
- provider schema version;
- index build timestamp;
- last failure state.

Freshness is advisory for query and diagnostic for UI. It must not mutate wiki
pages by itself.

## Rejected Alternatives

### Use `index.md` As The Machine Index

Rejected because `index.md` is optimized for humans and can change formatting
without intending to change retrieval semantics.

### Require Vector Search First

Rejected because it increases install complexity and contradicts the local
lightweight default.

### Put Indexing In Query Only

Rejected because ingest, lint, query, and UI all need a shared view of page
metadata and freshness.
