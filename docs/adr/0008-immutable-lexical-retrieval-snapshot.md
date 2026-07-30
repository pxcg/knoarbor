# ADR 0008: Immutable Lexical Retrieval Snapshot

## Status

Accepted

## Context

ADR 0007 defines two lexical locator channels that must share one bounded,
typed retrieval pipeline. The current implementation reconstructs atom and Raw
corpora during each query. That cannot provide stable pagination, trustworthy
no-match, predictable latency, or an immutable generation fence for Chat's
progressive retrieval loop.

KnoArbor is a local desktop product. The accepted baseline must not require a
vector database, embedding model, hosted search service, or a second runtime
daemon. It must also avoid two lexical implementations whose ranking semantics
can drift.

## Decision

KnoArbor persists one local SQLite FTS5 `LexicalSnapshot` per immutable
retrieval generation. `LexicalSnapshot` is the product contract; FTS5 is its
single baseline implementation.

The snapshot contains pre-tokenized fielded documents for:

- claims and their batch-scoped entity/relation locator metadata;
- Raw locator windows and their parent active SourceUnit identities;
- generation facts, field lengths, stable document identities, and the
  metadata required to produce typed recall signals.

Chinese and technical identifiers are normalized before insertion rather than
delegated to an environment-dependent tokenizer. Chinese bigrams are the main
recall terms, trigrams are precision features, and full phrases remain separate
rerank features. Latin identifiers preserve their original spelling plus
deterministic camel, snake, and kebab variants.

The machine-index owner publishes one verified composite generation:

```text
CompositeIndexGeneration {
  navigation_generation_id
  retrieval_generation_id
  active_fact_generation
}
```

The retrieval cursor binds `retrieval_generation_id`, query fingerprint, and
scope. A navigation-only rebuild may select a new composite generation without
invalidating a retrieval cursor when the retrieval generation is unchanged.

Each immutable factual revision may first compile a reusable normalized
RetrievalShard. Shards are build inputs, not independently queried indexes.
Publication always builds and verifies one global FTS5 snapshot so corpus
statistics and ranking are coherent. Active-head changes reuse unchanged
shards, compile changed shards, stage a complete generation, verify its fact
fence and hashes, and then replace `CURRENT` atomically.

Snapshot creation and repair belong to materialization/rebuild lifecycle code,
never to a read request. A missing, corrupt, stale, or FTS5-incapable runtime
returns a typed unavailable or integrity outcome. There is no per-request scan,
in-memory BM25, page search, or alternative postings fallback.

The desktop build and every supported Python runtime must prove FTS5 table
creation and query support before release. A runtime that cannot satisfy that
capability is unsupported; it does not silently select another scorer.

Retrieval snapshots are rebuildable derived data. Deleting them does not delete
active facts, Raw sources, Chat sessions, or user-authored material.

## Consequences

- Query latency and memory no longer grow through per-request corpus rebuilds.
- Stable cursors and no-match decisions can be tied to an exact retrieval
  generation.
- The local package gains no external service or model dependency.
- FTS5 capability becomes an explicit desktop/package release gate.
- Tokenization, field meaning, fusion, and answer sufficiency remain owned by
  specifications 1.38 and 1.10 rather than SQLite implementation details.
- Rebuild storage includes normalized revision shards and one global retrieval
  snapshot, both disposable derived artifacts.

## Alternatives Considered

### Keep Per-Request In-Memory BM25

Rejected because it rescans active records, cannot provide a durable snapshot
fence, and makes progressive paging expensive and unstable.

### Maintain FTS5 And A Custom Postings Fallback

Rejected because two scorers would create two retrieval authorities and make
ranking/no-match behavior dependent on packaging environment.

### Query Independent Revision Shards Directly

Rejected because BM25 corpus statistics would differ by shard and require an
additional cross-shard score-normalization policy.

### Add A Vector Database Or Embedding Model

Deferred. Dense retrieval is not required by the accepted lexical baseline and
may be considered only after fixed evaluation evidence shows a material recall
gap. It must still implement ADR 0007 identities and typed outcomes.

## Verification

- identical facts and configuration produce the same retrieval generation and
  ranked results;
- publication never exposes a partial SQLite database or mismatched fact
  generation;
- packaged macOS and Windows service artifacts pass an FTS5 capability probe;
- missing, corrupt, stale, and unsupported snapshots return typed outcomes and
  never invoke another scorer;
- navigation-only publication preserves `retrieval_generation_id` and existing
  retrieval cursor validity;
- changed active heads rebuild from reusable shards and return only current
  evidence identities;
- index deletion followed by lifecycle-owned rebuild does not mutate facts or
  user material.

## Follow-Up

- Specification 1.4 owns composite generation storage, verification, atomic
  publication, rebuild, and capability diagnostics.
- Specification 1.38 owns lexical document semantics, recall, fusion, cursor,
  active evidence resolution, and Query outcomes.
- Specification 1.10 owns bounded progressive planning over the shared
  retrieval snapshot.
