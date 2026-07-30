# ADR 0011: Raw-Grounded Graph-Assisted Retrieval

## Status

Superseded by [ADR 0018](0018-two-channel-raw-retrieval.md).

## Context

KnoArbor already publishes evidence-backed claims, canonical entities, and
relations, searches claim/entity/relation atoms together with active Raw
windows through one lexical Query path, and lets Chat issue progressive query
variants. A matched entity or relation currently resolves only to claims in the
same factual source batch. The query path does not traverse relations across
active source revisions, so cross-source connection questions depend on the
model guessing additional lexical queries.

The product does not currently need the cost and operating surface of a full
GraphRAG system. Hierarchical communities, pre-generated community summaries,
whole-vault map/reduce, an external graph service, embeddings, and a new graph
explorer would add substantial materialization, invalidation, evaluation, and
UI work whose benefit is concentrated in global corpus-analysis questions.

## Decision

KnoArbor will add graph-assisted retrieval inside the existing Raw-grounded
Query architecture.

```text
query text
  -> existing atom_claim + raw_lexical recall
  -> code resolves canonical entity seeds
  -> when relational evidence is required, enumerate active simple paths
     of at most two relation edges
  -> resolve every path edge through all supporting claims
  -> resolve those claims to active Raw source units and evidence spans
  -> fuse with existing evidence handles
  -> Chat reads active Raw and synthesizes as before
```

The following rules are durable:

1. Specification 1.4 publishes one verified cross-source relation adjacency in
   the same fact-fenced machine-index generation as lexical retrieval.
2. Specification 1.38 is the only graph traversal and retrieval-policy owner.
   Chat, API adapters, prompts, and the renderer do not traverse graph data.
3. Lexical recall supplies graph entry seeds. The first implementation adds no
   embedding model, vector index, HNSW index, or external graph database.
4. A returned path contains at most two relation edges, contains no repeated
   node, and is ordered deterministically. Depth is a product-semantic boundary;
   resource limits and continuation are independent safety boundaries.
5. Every relation edge retains every active supporting claim. Every graph-added
   evidence handle resolves through those claims to an active Raw source unit.
6. Graph paths are locator and explanation metadata. Active Raw remains the
   only local factual answer material and the only public factual citation.
7. Direct factual queries preserve the existing lexical fast path. Graph work
   is invoked only when code validates a relational request and at least one
   canonical seed.
8. If graph traversal is required but the graph generation is missing, stale,
   corrupt, cancelled, or safety-exhausted, Query returns that typed outcome. It
   does not convert the condition into `no_match` or silently use lexical-only
   semantics.
9. Active source revision replacement removes superseded edge and support
   contributions before the new generation is published.
10. The development index and Query schemas are replaced directly. There is no
    graph-on/off product mode, compatibility reader, or second Query pipeline.

## Explicit Non-Goals

- hierarchical community detection or community dossiers;
- model-authored community summaries;
- whole-vault global map/reduce;
- arbitrary-depth or open-ended graph walks;
- graph centrality as factual confidence;
- automatic entity merges beyond specification 1.27;
- new temporal, contradiction, or ontology semantics in specification 1.26;
- a new renderer graph-governance workflow;
- vector storage, an embedding service, or an external graph database.

## Consequences

Cross-source one- and two-relation questions can retrieve evidence that shares
canonical entities even when the final Raw wording does not repeat the original
query. The path is inspectable and evidence-closed without weakening the Raw
authority.

The design intentionally does not solve whole-corpus thematic questions or
paths longer than two relations. Those limitations are typed capability
boundaries, not hidden fallbacks. A future proposal may revisit them only with
quality evidence showing that their product value justifies the additional
materialization and evaluation cost.

## Ownership

- specification 1.4: active relation adjacency, support closure, generation
  binding, publication, verification, and recovery;
- specification 1.38: seed resolution, relational-plan validation, two-edge
  traversal, deterministic ordering, fusion, cursor, outcomes, and Raw closure;
- specification 1.10: reuse Query results in the existing progressive retrieval
  session and preserve locator-only path trace.

Specifications 1.6, 1.18, 1.26, and 1.27 retain their current contracts. This
initiative consumes their existing UI, answer, atom, and identity boundaries
without expanding them.

## Rejected Alternatives

### Full GraphRAG now

Rejected because communities, global summaries, map/reduce, identity review,
and new UI surfaces multiply implementation and validation cost before the
cross-source path value is proven.

### Repeated model query rewriting only

Rejected because it cannot deterministically discover or explain a connection
whose intermediate entity is absent from the user question.

### Use `graph_index.json` as retrieval authority

Rejected because it is a page-navigation projection and does not preserve the
active relation/claim/Raw evidence closure required by Query.

### Unlimited graph traversal

Rejected because high-degree nodes and cycles create unpredictable latency,
large evidence sets, and weakly related paths. The accepted semantic boundary
is at most two relation edges.

## Verification

Acceptance requires deterministic one- and two-edge cross-source fixtures,
alias-seeded paths, disconnected seeds, duplicate/cyclic paths, high-degree
resource exhaustion with continuation, stale revision exclusion, corrupt or
mismatched graph generations, Raw evidence closure, unchanged direct-query
behavior, and Chat citation integrity. Full tests, desktop packaging, and live
model checks run only when the actual changed closure or a release checkpoint
requires them.
