# ADR 0018: Two-Channel Raw Retrieval

## Status

Accepted

## Context

The graph-assisted relation channel added a second retrieval policy, graph
snapshot identity, traversal runtime, path response contract, and numeric
dependencies. Its bounded traversal did not improve the common personal
knowledge-base path enough to justify that complexity. Relation atoms are
already searchable through the atom index and already carry batch-local
`source_claim_ids` that close them to Claims and active Raw.

Document synthesis also appeared in two roles: first-stage document navigation
and atom retrieval. Only the navigation role is required. Treating synthesis as
retrievable evidence duplicates a whole-document summary beside exact
Claim/Relation and Raw locators and blurs the Raw authority boundary.

## Decision

Query has exactly two recall channels:

1. `atom_claim`: BM25 over Claim, Entity, and Relation atoms. A Relation match
   resolves through its batch-local `source_claim_ids`, then Claim evidence, to
   active Raw.
2. `raw_lexical`: BM25 over active Raw source units, preserving recovery from
   extraction misses.

Both channels fuse and deduplicate by active Raw identity before exact-span
selection and active evidence resolution. There is no relation-intent
classifier, graph traversal, graph snapshot, graph-specific score, path trace,
or graph/numeric runtime dependency.

Synthesis remains exactly once per document in
`active_corpus_outline.v1`. It is excluded from the retrieval FTS, candidates,
evidence, context pack, and public Query response. It can help the first model
choose a document region but cannot support an answer.

The development contracts are replaced directly:

- `lexical_snapshot.v7` excludes synthesis rows and graph artifacts;
- `index_generation_identity.v4` has no graph generation;
- `wiki_query.v4` has no relation-path response.

Derived indexes are rebuilt from active facts. Factual revisions and ingest
atoms are not migrated or rewritten.

## Consequences

- Query has one deterministic lexical architecture with two complementary Raw
  locator channels.
- Relation wording remains searchable without carrying graph traversal
  complexity.
- Cross-document multi-hop discovery is no longer claimed as a deterministic
  Query capability; the Retrieval Planner may select multiple document
  regions, and the answer model may synthesize only from returned Raw.
- Snapshot size and packaged desktop dependencies decrease.
- Synthesis improves document direction selection without entering the factual
  evidence plane.

## Supersession

This ADR fully supersedes ADR 0011. It narrows ADR 0017 by making explicit that
synthesis is absent from retrieval materialization as well as factual answer
material. ADRs 0007, 0008, 0015, 0016, and 0017 otherwise remain in force.

## Verification

- focused Query tests prove only `atom_claim` and `raw_lexical` statuses;
- a Relation atom resolves only through a Claim from its own source batch;
- no synthesis atom is materialized in the retrieval snapshot;
- schema replacement triggers a clean derived-index rebuild;
- public Query, API, Chat consumers, desktop packaging metadata, dependencies,
  and documentation contain no graph retrieval contract.

