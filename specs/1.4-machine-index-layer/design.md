# 1.4 Machine Index Layer Design

## Accepted Boundary

```text
active factual revisions + maintained projections
  -> compile/reuse normalized factual revision shards
  -> build navigation generation + global SQLite FTS5 retrieval generation
  -> stage one CompositeIndexGeneration
  -> verify fact fence, manifest, database capability, and all artifacts
  -> atomic CURRENT replacement
  -> one verified IndexSnapshot per reader
  -> UI navigation / graph / diagnostics + 1.38 lexical recall
```

`storage.wiki_index` owns generation construction and publication.
`storage.index_snapshot` owns generation lookup, manifest verification, artifact
hash verification, and snapshot identity. Runtime materialization owns when a
new build is required; readers do not publish or repair snapshots themselves.

The active composite generation identifies:

- `navigation_generation_id`;
- `retrieval_generation_id`;
- `active_fact_generation`.

Its navigation artifacts contain:

- `pages.json`: readable projection metadata;
- `links.json`: page navigation links;
- `sources.json`: source navigation metadata;
- `search.json`: deterministic navigation search records;
- `graph_index.json`: page graph payload.

Default knowledge query bypasses these page artifacts and opens the verified
SQLite FTS5 `LexicalSnapshot` owned by ADR 0008. Specification 1.38 defines its
fielded documents, query behavior, fusion, and active evidence semantics.

RetrievalShards are normalized immutable build inputs keyed by factual revision
content. Readers never query them independently. Publication merges the active
shards into one global database so document statistics remain coherent. A
navigation-only build may reuse the same retrieval generation; retrieval
cursors bind that ID and remain valid.

SQLite and FTS5 are implementation details behind `LexicalSnapshot`, but there
is only one production implementation. Build and release probes must create and
query an FTS5 table in the actual packaged service runtime. Capability failure
is explicit and has no runtime scorer fallback.

## Failure And Recovery

- missing `CURRENT`: report no active snapshot and request materialization where
  the caller owns recovery; a query reader never rebuilds inline;
- invalid generation ID, missing artifact, hash mismatch, or schema mismatch:
  readers fail explicitly; the startup lifecycle owner requests one clean
  materialization before admitting readers;
- unsupported lexical payload schema: rebuild a complete current-schema
  generation from active facts and atomically publish it; do not mutate the
  old database or active factual revisions;
- crash before `CURRENT`: staged/unselected generation remains unreachable;
- crash after `CURRENT`: the selected verified generation is readable and
  materialization state can finish idempotently.

## Rejected Alternatives

- provider classes with no production caller;
- Graph-led/page-BM25 fallback for default query;
- in-place mutation of active index JSON;
- rebuilding inside a read request without lifecycle ownership.
- querying per-revision shards and normalizing scores at request time;
- maintaining FTS5 and custom-postings implementations in parallel.

## Relation Atom Materialization

Relation atoms are indexed in the ordinary atom/claim FTS channel. Their
batch-local `source_claim_ids` remain locator edges to Claims and active Raw.
The machine index publishes no relation adjacency or graph generation.
