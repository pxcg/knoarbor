# 1.4 Machine Index Layer Verification

## Focused Automated Checks

```bash
uv run python -m unittest \
  tests.test_wiki_index_storage \
  tests.test_ingest_v5_architecture \
  tests.test_semantic_indexed_query \
  tests.test_architecture_governance
```

When the retrieval snapshot owner is implemented, add its focused storage and
packaged-capability test module to this command in the same change.

## Invariants To Inspect

- readers resolve artifacts only through the selected verified snapshot;
- the composite manifest binds navigation, retrieval, and active-fact
  generations without invalidating retrieval cursors on navigation-only builds;
- a corrupt manifest or artifact fails explicitly;
- a missing/stale retrieval snapshot or failed FTS5 capability probe never
  falls back to per-request BM25, page search, or another postings scorer;
- publication never exposes a partial generation;
- identical active facts and retrieval configuration produce the same
  retrieval generation and results;
- packaged macOS and Windows services create and query an FTS5 table at the
  release checkpoint;
- index deletion or rebuild does not delete factual revisions;
- startup replaces an unreadable or unsupported published snapshot before
  pruning, without adding a dual reader or query-time fallback;
- a v3-to-v4 lexical payload replacement leaves active facts byte-identical and
  keeps the prior generation selected until the complete v4 generation passes
  verification and is atomically published;
- default query imports no page-ranking provider and returns only active Raw
  evidence as factual material;
- no production or test import retains the removed Graph-led/provider path.

Broader packaging, live-model, or full-suite gates are required only when the
actual change reaches those boundaries or a release checkpoint.

## Cross-Source Relation Revision Assertions

- the selected composite manifest binds lexical, relation-graph, navigation,
  and active-fact generations;
- every graph relation preserves all supporting claims and every support edge
  resolves to an active Raw identity and valid span;
- source revision replacement removes every old node, edge, and support
  contribution before the new generation becomes visible;
- incremental shard reuse produces the same logical adjacency and support
  result as a clean rebuild;
- a crash or injected failure at each stage exposes either the prior verified
  generation or the complete new generation, never a mixed snapshot;
- relation-graph corruption, stale fact fences, and generation mismatch
  fail explicitly and never fall back to the navigation graph or lexical-only
  semantics;
- materialization invokes no LLM and does not mutate factual revisions, Raw,
  identity decisions, or Chat sessions.

Add focused relation-snapshot, incremental-equivalence, and fault-injection
modules to the command in the same implementation phase. Desktop
packaging is required only when the storage dependency or a release checkpoint
reaches the packaged runtime.
